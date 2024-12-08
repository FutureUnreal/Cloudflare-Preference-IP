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
        eval_config = config['evaluation']
        
        # Ping测试阈值
        latency_config = eval_config.get('latency_thresholds', {})
        self.latency_thresholds = {
            'TELECOM': latency_config.get('telecom_latency_threshold', 100),
            'UNICOM': latency_config.get('unicom_latency_threshold', 100),
            'MOBILE': latency_config.get('mobile_latency_threshold', 100),
            'OVERSEAS': latency_config.get('overseas_latency_threshold', 150),
            'DEFAULT': latency_config.get('default_latency_threshold', 150)
        }
        
        # HTTP测试阈值
        self.http_thresholds = {
            'ttfb': eval_config.get('http_ttfb_threshold', 200),      # 首字节时间阈值(ms)
            'total_time': eval_config.get('http_total_time_threshold', 1000),  # 总加载时间阈值(ms)
            'success_rate': eval_config.get('http_success_rate', 0.8)  # HTTP测试成功率要求
        }
        
        # 评分权重
        self.weights = {
            'ping': {
                'latency': 0.4,        # Ping延迟权重
                'loss': 0.2,           # 丢包率权重
                'stability': 0.2       # 稳定性权重
            },
            'http': {
                'ttfb': 0.1,          # 首字节时间权重
                'total_time': 0.1      # 总加载时间权重
            }
        }
        
        # ISP权重
        self.isp_weights = {
            'TELECOM': 0.35,
            'UNICOM': 0.25,
            'MOBILE': 0.25,
            'OVERSEAS': 0.15
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

    def calculate_score(self, test_result: Dict, isp: str = None) -> float:
        """计算IP综合得分"""
        try:
            final_score = 0
            
            # 1. 计算Ping测试得分
            ping_scores = self._calculate_ping_scores(test_result)
            ping_total = sum(score * self.isp_weights[isp] 
                        for isp, score in ping_scores.items())
            
            # 2. 计算HTTP测试得分
            http_score = self._calculate_http_score(test_result.get('http_test', {}), isp)
            
            # 3. 计算加权总分
            final_score = (ping_total * sum(self.weights['ping'].values()) + 
                        http_score * sum(self.weights['http'].values()))
            
            # 4. 应用惩罚因子
            penalties = self._calculate_penalties(test_result)
            final_score *= penalties
            
            return final_score
            
        except Exception as e:
            self.logger.error(f"计算得分时出错: {str(e)}")
            return 0
        
    def _calculate_ping_scores(self, test_result: Dict) -> Dict[str, float]:
        """计算各ISP的Ping测试得分"""
        scores = {}
        
        for isp, result in test_result.get('tests', {}).items():
            if not result.get('available', False):
                continue
                
            # 延迟得分
            latency = result.get('latency', float('inf'))
            latency_score = max(0, 100 - (latency / self.latency_thresholds[isp]) * 100)
            
            # 丢包得分
            loss = result.get('loss', 100)
            loss_score = max(0, 100 - loss)
            
            # 稳定性得分 (基于延迟标准差)
            stability = result.get('stability', 100)
            stability_score = max(0, 100 - stability)
            
            # 计算加权得分
            scores[isp] = (
                latency_score * self.weights['ping']['latency'] +
                loss_score * self.weights['ping']['loss'] +
                stability_score * self.weights['ping']['stability']
            )
            
        return scores

    def _calculate_http_score(self, http_result: Dict, isp: str) -> float:
        """计算HTTP测试得分"""
        if not http_result or not http_result.get('available', False):
            self.logger.info("HTTP测试结果为空或不可用")
            return 0
            
        results = http_result.get('results', {})
        
        # 根据ISP选择合适的DNS测试结果
        if isp in ['TELECOM', 'UNICOM', 'MOBILE']:
            aliyun_result = results.get('ALIYUN', {})
            baidu_result = results.get('BAIDU', {})
            valid_results = []
            
            if aliyun_result.get('available', False):
                valid_results.append(aliyun_result)
            if baidu_result.get('available', False):
                valid_results.append(baidu_result)
                
            if not valid_results:
                self.logger.info("没有可用的国内DNS测试结果")
                return 0
                
            # 使用延迟最低的结果
            test_result = min(valid_results, key=lambda x: x.get('ttfb', float('inf')))
            self.logger.info(f"选择最佳结果: {test_result}")
        
        elif isp == 'OVERSEAS':
            # 境外线路使用谷歌DNS的结果
            test_result = results.get('GOOGLE', {})
            if not test_result.get('available', False):
                self.logger.info("谷歌DNS测试不可用")
                return 0
        
        else:  # DEFAULT
            # 默认线路使用所有DNS中最好的结果
            valid_results = [r for r in results.values() if r.get('available', False)]
            if not valid_results:
                self.logger.info("没有可用的DNS测试结果")
                return 0
            test_result = min(valid_results, key=lambda x: x.get('ttfb', float('inf')))
        
        # 计算得分
        ttfb = test_result.get('ttfb', float('inf'))
        ttfb_score = max(0, 100 - (ttfb / self.http_thresholds['ttfb']) * 100)
        
        total_time = test_result.get('total_time', float('inf'))
        time_score = max(0, 100 - (total_time / self.http_thresholds['total_time']) * 100)
        
        final_score = (ttfb_score * self.weights['http']['ttfb'] +
                time_score * self.weights['http']['total_time'])
        
        return final_score

    def _calculate_penalties(self, test_result: Dict) -> float:
        """计算惩罚因子"""
        penalty = 1.0
        
        # 1. 如果HTTP测试完全失败，严重降分
        if not test_result.get('http_test', {}).get('available', False):
            penalty *= 0.5
            
        # 2. 如果某些关键ISP测试失败，也要降分
        key_isps = {'TELECOM', 'UNICOM', 'MOBILE'}
        failed_key_isps = sum(1 for isp in key_isps 
                            if not test_result.get('tests', {}).get(isp, {}).get('available', False))
        if failed_key_isps > 0:
            penalty *= (1 - 0.2 * failed_key_isps)
            
        # 3. 如果延迟波动太大，适当降分
        for isp_result in test_result.get('tests', {}).values():
            if isp_result.get('latency_variance', 0) > 50:  # 延迟方差超过50ms
                penalty *= 0.9
                
        return penalty

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
            
            if 'tests' not in result:
                self.logger.warning(f"IP {ip} 没有tests字段")
                continue

            for isp, test in result['tests'].items():            
                if not test.get('available', False):
                    self.logger.info(f"{isp} 测试不可用")
                    continue
                    
                latency = test.get('latency', float('inf'))
                threshold = self.latency_thresholds.get(isp, float('inf'))
                
                if latency < threshold:
                    # 计算HTTP得分
                    http_result = result.get('http_test', {})
                    http_score = self._calculate_http_score(http_result, isp)
                    
                    if http_score > 0:
                        score = self.calculate_score(result, isp)
                        self.logger.info(f"{isp} 总得分: {score}")
                        
                        evaluations[isp].append({
                            'ip': ip,
                            'score': score,
                            'latency': latency,
                            'loss': test.get('loss', 0),
                            'http_score': http_score,
                            'node_id': test.get('node_id')
                        })
                        self.logger.info(f"已添加到 {isp} 评估结果")
                    else:
                        self.logger.info(f"{isp} HTTP得分为0，未通过评估")
                else:
                    self.logger.info(f"{isp} 延迟超出阈值 ({latency}ms > {threshold}ms)，未通过评估")

            # 处理默认线路
            if any(test.get('available', False) for test in result['tests'].values()):
                self.logger.info("\n处理默认线路:")
                # 计算平均延迟
                valid_tests = [test for test in result['tests'].values() 
                            if test.get('available', False)]
                avg_latency = sum(t['latency'] for t in valid_tests) / len(valid_tests)
                self.logger.info(f"默认线路平均延迟: {avg_latency}ms")
                
                if avg_latency < self.latency_thresholds['DEFAULT']:
                    http_score = self._calculate_http_score(result.get('http_test', {}), 'DEFAULT')
                    
                    if http_score > 0:
                        score = self.calculate_score(result, 'DEFAULT')
                        
                        evaluations['DEFAULT'].append({
                            'ip': ip,
                            'score': score,
                            'latency': avg_latency,
                            'loss': sum(t.get('loss', 0) for t in valid_tests) / len(valid_tests),
                            'http_score': http_score
                        })
                    else:
                        self.logger.info("默认线路 HTTP得分为0，未通过评估")
                else:
                    self.logger.info(f"默认线路延迟超出阈值 ({avg_latency}ms > {self.latency_thresholds['DEFAULT']}ms)，未通过评估")
        
        # 最终结果汇总
        for isp, ips in evaluations.items():
            self.logger.info(f"\n{isp} 最终评估结果: {len(ips)} 个IP")
            for ip_data in ips:
                self.logger.info(f"IP: {ip_data['ip']}, 得分: {ip_data['score']:.2f}, "
                            f"延迟: {ip_data['latency']:.1f}ms, HTTP得分: {ip_data['http_score']:.2f}")
        
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