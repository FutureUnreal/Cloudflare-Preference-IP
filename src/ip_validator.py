import random
import asyncio
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass

@dataclass
class TestResult:
    node_id: str
    latency: float
    available: bool
    loss: float = 0
    http_performance: Dict = None  # 新增HTTP性能字段

class IPValidator:
    def __init__(self, config: Dict):
        self.config = config
        self.logger = logging.getLogger('IPValidator')
        
        # 初始化测试节点配置
        self.NODE_IDS = {
            'TELECOM': [
                '1227', '1312', '1169', '1135', '1310', 
                '1132', '1214', '1311', '1138', '1304'
            ],
            'UNICOM': [
                '1254', '1275', '1278', '1264', '1273', 
                '1266', '1276', '1277', '1253', '1226'
            ],
            'MOBILE': [
                '1249', '1237', '1290', '1294', '1250', 
                '1295', '1287', '1242', '1245', '1283'
            ],
            'OVERSEAS': [
                '1340', '1341', '1343', '1345'
            ]
        }
        
        # 每个运营商验证时使用的节点数量（一半）
        self.validation_nodes_count = {
            'TELECOM': len(self.NODE_IDS['TELECOM']) // 2,
            'UNICOM': len(self.NODE_IDS['UNICOM']) // 2,
            'MOBILE': len(self.NODE_IDS['MOBILE']) // 2,
            'OVERSEAS': len(self.NODE_IDS['OVERSEAS']) // 2
        }
        
        # 从配置文件加载阈值
        self.latency_thresholds = {
            'TELECOM': config['evaluation']['latency_thresholds']['telecom_latency_threshold'],
            'UNICOM': config['evaluation']['latency_thresholds']['unicom_latency_threshold'],
            'MOBILE': config['evaluation']['latency_thresholds']['mobile_latency_threshold'],
            'OVERSEAS': config['evaluation']['latency_thresholds']['overseas_latency_threshold']
        }
        
        # HTTP性能阈值
        self.http_thresholds = {
            'ttfb': config['evaluation'].get('http_ttfb_threshold', 200),
            'total_time': config['evaluation'].get('http_total_time_threshold', 1000)
        }
        
        # 验证成功所需的达标节点比例
        self.success_ratio = config.get('validation', {}).get('success_ratio', 0.8)
        self.http_success_ratio = config.get('validation', {}).get('http_success_ratio', 0.7)

    async def validate_ip(self, ip: str, isp: str, initial_result: Dict) -> Optional[Dict]:
        """对初步达标的IP进行多节点验证"""
        self.logger.info(f"开始对IP {ip} 进行 {isp} 多节点验证")
        
        try:
            # 随机选择验证节点（排除已使用的节点）
            used_node = initial_result.get('node_id')
            available_nodes = [node for node in self.NODE_IDS[isp] if node != used_node]
            validation_count = self.validation_nodes_count[isp]
            
            if len(available_nodes) < validation_count:
                self.logger.warning(f"可用节点数量不足，需要 {validation_count} 个，实际只有 {len(available_nodes)} 个")
                return None
                
            selected_nodes = random.sample(available_nodes, validation_count)
            
            # 并发测试所有选中的节点
            ping_tasks = [self._test_single_node(ip, node) for node in selected_nodes]
            ping_results = await asyncio.gather(*ping_tasks)
            
            # HTTP测试验证
            http_result = await self._validate_http_performance(ip, isp)
            
            # 评估ping测试结果
            valid_ping_results = [r for r in ping_results if r and r.available and 
                                r.latency <= self.latency_thresholds[isp]]
            ping_success_rate = len(valid_ping_results) / len(ping_results)
            
            self.logger.info(f"Ping 验证结果: 总计 {len(ping_results)} 个节点, "
                           f"达标 {len(valid_ping_results)} 个, "
                           f"成功率 {ping_success_rate:.2%}")
            
            # 判断是否通过验证
            if ping_success_rate >= self.success_ratio and http_result.get('available', False):
                # 计算平均延迟（只考虑有效结果）
                avg_latency = sum(r.latency for r in valid_ping_results) / len(valid_ping_results)
                
                # 返回完整的测试结果
                return {
                    'latency': avg_latency,
                    'available': True,
                    'loss': sum(r.loss for r in valid_ping_results) / len(valid_ping_results),
                    'node_id': ','.join(selected_nodes),  # 记录所有测试节点
                    'http_performance': http_result,      # 添加HTTP性能数据
                    'validation_results': {
                        'ping': [
                            {
                                'node_id': r.node_id,
                                'latency': r.latency,
                                'available': r.available,
                                'loss': r.loss
                            } for r in ping_results
                        ],
                        'http': http_result
                    }
                }
            
            self.logger.warning(f"IP {ip} 在 {isp} 的多节点验证未通过")
            return None
            
        except Exception as e:
            self.logger.error(f"验证过程出错: {str(e)}")
            return None

    async def _validate_http_performance(self, ip: str, isp: str) -> Dict:
        """验证HTTP性能"""
        try:
            # 使用HTTPTester进行测试
            from src.http_tester import HTTPTester
            http_tester = HTTPTester(self.config)
            result = await http_tester.test_ip(ip)
            
            # 根据ISP选择合适的DNS结果进行验证
            if isp in ['TELECOM', 'UNICOM', 'MOBILE']:
                # 国内线路验证阿里DNS和百度DNS的结果
                dns_results = [
                    result['results'].get('ALIYUN', {}),
                    result['results'].get('BAIDU', {})
                ]
                valid_results = [r for r in dns_results if r.get('available', False)]
                if not valid_results:
                    return {'available': False, 'error': '国内DNS测试失败'}
                
                # 使用最好的结果
                best_result = min(valid_results, key=lambda x: x.get('ttfb', float('inf')))
                if (best_result['ttfb'] <= self.http_thresholds['ttfb'] and
                    best_result['total_time'] <= self.http_thresholds['total_time']):
                    return {'available': True, **best_result}
                
            elif isp == 'OVERSEAS':
                # 境外线路验证谷歌DNS的结果
                google_result = result['results'].get('GOOGLE', {})
                if not google_result.get('available', False):
                    return {'available': False, 'error': '谷歌DNS测试失败'}
                
                if (google_result['ttfb'] <= self.http_thresholds['ttfb'] * 1.5 and  # 境外阈值放宽50%
                    google_result['total_time'] <= self.http_thresholds['total_time'] * 1.5):
                    return {'available': True, **google_result}
            
            return {'available': False, 'error': 'HTTP性能未达标'}
            
        except Exception as e:
            self.logger.error(f"HTTP性能验证失败: {str(e)}")
            return {'available': False, 'error': str(e)}

    async def _test_single_node(self, ip: str, node_id: str) -> Optional[TestResult]:
        """使用单个节点测试IP"""
        try:
            from src.ip_tester import IPTester
            tester = IPTester(self.config)
            result = await tester.test_single_ip(ip, node_id)
            
            return TestResult(
                node_id=node_id,
                latency=result.get('latency', float('inf')),
                available=result.get('available', False),
                loss=result.get('loss', 100)
            )
            
        except Exception as e:
            self.logger.error(f"节点 {node_id} 测试失败: {str(e)}")
            return None

    async def batch_validate(self, evaluations: Dict[str, List[Dict]]) -> Dict[str, List[Dict]]:
        """批量验证评估结果"""
        validated_results = {
            'TELECOM': [],
            'UNICOM': [],
            'MOBILE': [],
            'OVERSEAS': [],
            'DEFAULT': []  # 默认线路保持不变
        }
        
        # 只验证有达标IP的运营商
        for isp, results in evaluations.items():
            if isp == 'DEFAULT' or not results:  # 跳过默认线路和空结果
                validated_results[isp] = results
                continue
                
            self.logger.info(f"开始验证 {isp} 的 {len(results)} 个IP")
            for result in results:
                ip = result['ip']
                self.logger.info(f"验证 {isp} IP: {ip}")
                
                validated = await self.validate_ip(ip, isp, result)
                if validated:
                    validated_results[isp].append({
                        **result,
                        **validated
                    })
                        
        return validated_results