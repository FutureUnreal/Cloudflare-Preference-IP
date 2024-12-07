import logging
import statistics
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Union, Optional

class IPEvaluator:
    def __init__(self, config: Dict):
        self.config = config
        self.setup_logging()
        
        # 评估阈值配置
        eval_config = config['evaluation']  # 先获取 evaluation 配置
        self.latency_thresholds = {
            'TELECOM': eval_config.get('telecom_latency_threshold', 150),
            'UNICOM': eval_config.get('unicom_latency_threshold', 150),
            'MOBILE': eval_config.get('mobile_latency_threshold', 150),
            'OVERSEAS': eval_config.get('overseas_latency_threshold', 200),
            'DEFAULT': eval_config.get('default_latency_threshold', 450)
        }
        
        self.stability_thresholds = {
            'DOMESTIC': config.get('stability_threshold', 30),
            'OVERSEAS': config.get('overseas_stability_threshold', 50)
        }
        
        self.min_success_rate = config.get('min_success_rate', 0.8)
        self.max_loss_rate = config.get('max_loss_rate', 20)
        self.domestic_latency_threshold = config.get('domestic_latency_threshold', 200)
        self.overseas_good_latency = config.get('overseas_good_latency', 150)
        
        # 运营商权重
        self.isp_weights = {
            'TELECOM': 0.4,
            'UNICOM': 0.3,
            'MOBILE': 0.3,
            'OVERSEAS': 1.0
        }

    def setup_logging(self):
        """设置日志"""
        log_dir = Path('logs')
        log_dir.mkdir(exist_ok=True)
        
        self.logger = logging.getLogger('IPEvaluator')
        if not self.logger.handlers:
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            
            fh = logging.FileHandler(
                log_dir / f'evaluator_{datetime.now():%Y%m%d}.log'
            )
            fh.setFormatter(formatter)
            fh.setLevel(logging.INFO)
            
            ch = logging.StreamHandler()
            ch.setFormatter(formatter)
            ch.setLevel(logging.INFO)
            
            self.logger.addHandler(fh)
            self.logger.addHandler(ch)
            self.logger.setLevel(logging.INFO)

    def is_overseas_ip(self, test_result: Dict) -> bool:
        """根据测试结果判断是否为境外 IP"""
        domestic_failed = True
        domestic_high_latency = True
        overseas_good = False
        
        # 检查国内运营商测试结果
        for isp in ['TELECOM', 'UNICOM', 'MOBILE']:
            if isp in test_result['tests']:
                result = test_result['tests'][isp]
                if result.get('available', False):
                    domestic_failed = False
                    if result.get('latency', float('inf')) < self.domestic_latency_threshold:
                        domestic_high_latency = False
        
        # 检查境外节点测试结果
        if 'OVERSEAS' in test_result['tests']:
            result = test_result['tests']['OVERSEAS']
            if (result.get('available', False) and 
                result.get('latency', float('inf')) < self.overseas_good_latency):
                overseas_good = True
        
        return (domestic_failed or domestic_high_latency) and overseas_good

    def calculate_latency_score(self, latency: float, threshold: float) -> float:
        """计算延迟得分"""
        if latency >= float('inf') or latency <= 0:
            return 0
        return max(0, 100 - (latency / threshold) * 100)

    def calculate_loss_score(self, loss: float) -> float:
        """计算丢包得分"""
        return max(0, 100 - (loss / self.max_loss_rate) * 100)

    def calculate_stability_score(self, latencies: List[float], is_overseas: bool = False) -> float:
        """计算稳定性得分"""
        if len(latencies) < 2:
            return 100
        
        try:
            std_dev = statistics.stdev(latencies)
            threshold = (self.stability_thresholds['OVERSEAS'] if is_overseas 
                        else self.stability_thresholds['DOMESTIC'])
            return max(0, 100 - (std_dev / threshold) * 100)
        except statistics.StatisticsError:
            return 0

    def calculate_score(self, test_result: Dict) -> float:
        """计算单个IP的综合得分"""
        try:
            scores = []
            is_overseas = self.is_overseas_ip(test_result)
            
            # 选择评分权重
            weights = ({'OVERSEAS': 1.0} if is_overseas else self.isp_weights)
            
            for isp, weight in weights.items():
                if isp not in test_result['tests']:
                    continue
                    
                isp_result = test_result['tests'][isp]
                if not isp_result.get('available', False):
                    continue
                
                latency = isp_result.get('latency', float('inf'))
                loss = isp_result.get('loss', 100)
                
                if latency < float('inf'):
                    latency_score = self.calculate_latency_score(
                        latency, 
                        self.latency_thresholds[isp]
                    )
                    loss_score = self.calculate_loss_score(loss)
                    
                    score = (latency_score * 0.7 + loss_score * 0.3) * weight
                    scores.append(score)
            
            return sum(scores) if scores else 0
            
        except Exception as e:
            self.logger.error(f"Error calculating score: {str(e)}")
            return 0

    def evaluate_batch(self, test_results: List[Dict]) -> Dict[str, List[Dict]]:
        evaluations = {
            'TELECOM': [],
            'UNICOM': [],
            'MOBILE': [],
            'OVERSEAS': [],
            'DEFAULT': []
        }
        
        for result in test_results:
            ip = result['ip']
            self.logger.info(f"\n评估IP {ip}:")
            
            # 先打印完整的测试结果
            self.logger.info(f"测试结果详情: {json.dumps(result, indent=2, ensure_ascii=False)}")
            
            # 检查tests字段
            if 'tests' not in result:
                self.logger.warning(f"IP {ip} 没有tests字段")
                continue
                
            # 遍历所有测试结果
            for isp, test in result['tests'].items():
                self.logger.info(f"{isp} 测试结果: {test}")
                
                if test.get('available', False):
                    latency = test.get('latency', float('inf'))
                    threshold = self.latency_thresholds.get(isp, float('inf'))
                    self.logger.info(f"{isp}: 延迟={latency}ms, 阈值={threshold}ms")
                    
                    # 如果延迟小于阈值，添加到评估结果
                    if latency < threshold:
                        evaluations[isp].append({
                            'ip': ip,
                            'score': self.calculate_latency_score(latency, threshold),
                            'latency': latency,
                            'loss': test.get('loss', 0),
                            'node_id': test.get('node_id')
                        })
                        self.logger.info(f"添加到 {isp} 评估结果")
                else:
                    self.logger.info(f"{isp}: 测试不可用")

            # 计算默认线路的评估
            available_tests = [
                test for isp, test in result['tests'].items() 
                if test.get('available', False) and isp in ['TELECOM', 'UNICOM', 'MOBILE', 'OVERSEAS']
            ]
            
            if available_tests:
                avg_latency = statistics.mean(
                    test['latency'] for test in available_tests
                )
                threshold = self.config['evaluation']['default_latency_threshold']
                self.logger.info(f"DEFAULT 线路评估: 平均延迟={avg_latency}ms, 阈值={threshold}ms")
                
                if avg_latency < threshold:
                    evaluations['DEFAULT'].append({
                        'ip': ip,
                        'score': self.calculate_latency_score(avg_latency, threshold),
                        'latency': avg_latency,
                        'loss': statistics.mean(test.get('loss', 0) for test in available_tests),
                        'tests_count': len(available_tests)
                    })
                    self.logger.info("添加到 DEFAULT 评估结果")
        
        # 打印最终评估结果
        for isp, results in evaluations.items():
            self.logger.info(f"{isp} 评估结果: {len(results)} 个IP")
            for ip_info in results:
                self.logger.info(f"  IP: {ip_info['ip']}, 延迟: {ip_info['latency']}ms")
        
        return evaluations

    def is_qualified(self, test_result: Dict) -> bool:
        """判断IP是否达到质量标准"""
        try:
            available_count = 0
            total_latency = 0
            latencies = []
            is_overseas = self.is_overseas_ip(test_result)
            
            for isp_result in test_result['tests'].values():
                if isp_result.get('available', False):
                    available_count += 1
                    latency = isp_result.get('latency', float('inf'))
                    if latency < float('inf'):
                        total_latency += latency
                        latencies.append(latency)
            
            if not latencies:
                return False
                
            success_rate = available_count / len(test_result['tests'])
            avg_latency = total_latency / len(latencies)
            
            # 计算稳定性得分
            stability_score = self.calculate_stability_score(latencies, is_overseas)
            
            # 根据是否是境外IP使用不同的阈值
            latency_threshold = (self.latency_thresholds['OVERSEAS'] if is_overseas
                               else max(self.latency_thresholds[isp] for isp in ['TELECOM', 'UNICOM', 'MOBILE']))
            
            return (success_rate >= self.min_success_rate and
                   avg_latency <= latency_threshold and
                   stability_score >= 60)
                   
        except Exception as e:
            self.logger.error(f"Error checking qualification: {str(e)}")
            return False

    def get_best_ips(self, evaluations: Dict[str, List[Dict]], 
                     limit: Optional[int] = None) -> Dict[str, List[str]]:
        """获取每个运营商最佳的IP列表"""
        try:
            best_ips = {}
            for isp, results in evaluations.items():
                if limit:
                    best_ips[isp] = [r['ip'] for r in results[:limit]]
                else:
                    best_ips[isp] = [r['ip'] for r in results]
            return best_ips
        except Exception as e:
            self.logger.error(f"Error getting best IPs: {str(e)}")
            return {}