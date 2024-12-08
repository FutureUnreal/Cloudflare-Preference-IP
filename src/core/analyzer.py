import logging
import statistics
from pathlib import Path
from typing import Dict, List
from datetime import datetime, timedelta
import asyncio
import json

class IPHistoryAnalyzer:
   def __init__(self, config: Dict):
       self.config = config
       self.setup_logging()
       
       # 基本配置
       self.results_dir = Path(config.get('results_dir', 'results'))
       self.analysis_days = config.get('analysis_days', 7)
       self.min_samples = config.get('min_samples', 5)
        
       # 调试日志
       self.logger.info(f"初始化 IPHistoryAnalyzer:")
       self.logger.info(f"  结果目录: {self.results_dir}")
       self.logger.info(f"  分析天数: {self.analysis_days}")
       self.logger.info(f"  最小样本数: {self.min_samples}")
        
       # 加载历史记录
       self.history = self._load_history()
       self.logger.info(f"加载了 {len(self.history)} 个IP的历史记录")
       self.bad_ips = self._load_bad_ips()
       
       # 分析参数
       self.analysis_days = config.get('analysis_days', 7)  
       self.min_samples = config.get('min_samples', 10)    
       self.latency_volatility_threshold = config.get('latency_volatility', 0.3)
       self.availability_threshold = config.get('availability_threshold', 0.9)

       self.http_weights = {
            'DOMESTIC': {
                'ALIYUN': 0.5,
                'BAIDU': 0.5
            },
            'OVERSEAS': {
                'GOOGLE': 1.0
            }
        }

   async def analyze_and_update(self, current_ips: Dict[str, List[str]], 
                    new_test_results: Dict[str, List[Dict]]) -> Dict[str, List[str]]:
        try:
            optimized_ips = {
                'TELECOM': [],
                'UNICOM': [],
                'MOBILE': [],
                'OVERSEAS': [],
                'DEFAULT': []
            }

            for isp in optimized_ips.keys():
                # 计算当前IP的得分
                current_ip_scores = {}
                if isp in current_ips:
                    for ip in current_ips[isp]:
                        score = await self._calculate_historical_score(ip, isp)
                        if score > 0:
                            current_ip_scores[ip] = score

                # 处理新测试的IP
                new_ip_scores = {}
                if isp in new_test_results:
                    for result in new_test_results[isp]:
                        ip = result['ip']
                        latency = result['latency']
                        # 计算综合得分，考虑 HTTP 性能
                        latency_score = 1000 / latency if latency > 0 else 0
                        http_score = 0
                        if 'http_test' in result and result['http_test'].get('available', False):
                            ttfb = result['http_test'].get('ttfb', float('inf'))
                            total_time = result['http_test'].get('total_time', float('inf'))
                            if ttfb < float('inf') and total_time < float('inf'):
                                http_score = (1000 / ttfb + 1000 / total_time) / 2
                        score = latency_score * 0.7 + http_score * 0.3
                        if score > 0:
                            new_ip_scores[ip] = score

                # 合并得分并排序
                all_scores = {**current_ip_scores, **new_ip_scores}
                sorted_ips = sorted(
                    all_scores.items(),
                    key=lambda x: (-x[1], x[0])  # 按得分降序，IP升序
                )

                # 选择最优IP
                max_records = self.config['dns']['max_records_per_line'].get(isp, 1)
                selected_ips = [ip for ip, _ in sorted_ips[:max_records]]
                
                if selected_ips:
                    optimized_ips[isp] = selected_ips
                    self.logger.info(f"{isp} 最终选择IP: {selected_ips}")

            return optimized_ips

        except Exception as e:
            self.logger.error(f"IP分析失败: {str(e)}")
            return current_ips
        
   def _load_bad_ips(self) -> Dict:
        """加载不良IP记录"""
        bad_ips_file = self.results_dir / 'bad_ips.json'
        if bad_ips_file.exists():
            try:
                with open(bad_ips_file) as f:
                    return json.load(f)
            except Exception as e:
                self.logger.error(f"加载不良IP记录失败: {str(e)}")
        return {}
   
   async def _analyze_ip_batch(self, ips: List[str]) -> Dict[str, float]:
       """批量分析IP历史表现"""
       scores = {}
       
       for ip in ips:
           scores[ip] = await self._calculate_historical_score(ip)
           
       return scores

   async def _calculate_historical_score(self, ip: str, isp: str) -> float:
        """计算特定IP在特定线路的历史得分"""
        try:
            if ip not in self.history:
                self.logger.info(f"IP {ip} 没有历史记录")
                return 0

            record = self.history[ip]
            last_update = datetime.fromisoformat(record['last_update'])
            update_count = record['update_count']
            
            # 检查记录是否过期
            days_old = (datetime.now() - last_update).days
            if days_old > self.analysis_days:
                self.logger.info(f"IP {ip} 的记录已过期 ({days_old} 天)")
                return 0

            # 1. 计算延迟得分
            latency_score = 0
            if isp in record['latency']:
                latency = record['latency'][isp]
                latency_score = 1000 / latency if latency > 0 else 0
            
            # 2. 计算HTTP性能得分
            http_score = 0
            if 'http_performance' in record:
                if isp in ['TELECOM', 'UNICOM', 'MOBILE']:
                    # 国内线路使用阿里DNS和百度DNS的加权平均
                    aliyun_score = self._calculate_dns_http_score(
                        record['http_performance'], 'ALIYUN'
                    )
                    baidu_score = self._calculate_dns_http_score(
                        record['http_performance'], 'BAIDU'
                    )
                    
                    weights = self.http_weights['DOMESTIC']
                    if aliyun_score > 0 and baidu_score > 0:
                        http_score = (
                            aliyun_score * weights['ALIYUN'] +
                            baidu_score * weights['BAIDU']
                        )
                    elif aliyun_score > 0:
                        http_score = aliyun_score
                    elif baidu_score > 0:
                        http_score = baidu_score
                        
                elif isp == 'OVERSEAS':
                    # 境外线路使用谷歌DNS
                    http_score = self._calculate_dns_http_score(
                        record['http_performance'], 'GOOGLE'
                    )
                else:  # DEFAULT
                    # 使用所有DNS中最好的得分
                    scores = []
                    for dns_type in ['ALIYUN', 'BAIDU', 'GOOGLE']:
                        score = self._calculate_dns_http_score(
                            record['http_performance'], dns_type
                        )
                        if score > 0:
                            scores.append(score)
                    http_score = max(scores) if scores else 0
            
            # 3. 计算稳定性加分
            stability_bonus = min(10, update_count * 1)
            
            # 4. 计算最终得分
            final_score = (
                latency_score * 0.6 +   # 延迟权重提高
                http_score * 0.3 +      # HTTP性能占比提高
                stability_bonus * 0.1    # 稳定性保持不变
            )
            
            self.logger.info(
                f"IP {ip} {isp} 得分计算:\n"
                f"  延迟得分: {latency_score:.2f}\n"
                f"  HTTP得分: {http_score:.2f}\n"
                f"  稳定性加分: {stability_bonus}\n"
                f"  最终得分: {final_score:.2f}"
            )
            
            return final_score

        except Exception as e:
            self.logger.error(f"计算IP {ip} 历史得分时出错: {str(e)}")
            return 0
        
   def _calculate_dns_http_score(self, http_performance: Dict, dns_type: str) -> float:
        """计算特定DNS的HTTP性能得分"""
        try:
            ttfb_values = []
            total_time_values = []
            
            # 获取该DNS服务器的所有测试结果
            for url, ttfb in http_performance['ttfb'].items():
                if url.startswith(dns_type):
                    ttfb_values.append(ttfb)
                    
            for url, total_time in http_performance['total_time'].items():
                if url.startswith(dns_type):
                    total_time_values.append(total_time)
            
            if not ttfb_values or not total_time_values:
                return 0
                
            # 计算平均值
            avg_ttfb = statistics.mean(ttfb_values)
            avg_total_time = statistics.mean(total_time_values)
            
            # 计算得分
            ttfb_score = 1000 / avg_ttfb if avg_ttfb > 0 else 0
            time_score = 1000 / avg_total_time if avg_total_time > 0 else 0
            
            return (ttfb_score + time_score) / 2
            
        except Exception as e:
            self.logger.error(f"计算DNS {dns_type} HTTP得分失败: {str(e)}")
            return 0

   def _select_optimal_ips(self, current_scores: Dict[str, float], 
                         new_scores: Dict[str, float], max_ips: int) -> List[str]:
       """选择最优IP组合"""
       try:
           # 合并所有IP得分
           all_scores = {**current_scores, **new_scores}
           
           # 按得分排序
           sorted_ips = sorted(
               all_scores.items(),
               key=lambda x: (-x[1], x[0])  # 按得分降序，相同得分按IP排序
           )
           
           # 选择得分最高的IP
           selected_ips = []
           for ip, score in sorted_ips:
               if len(selected_ips) >= max_ips:
                   break
                   
               if score > 0:  # 只选择有效的IP
                   selected_ips.append(ip)
           
           # 如果没有足够的合格IP，保留部分现有IP
           if len(selected_ips) < max_ips:
               current_ips = set(current_scores.keys())
               for ip, _ in sorted_ips:
                   if len(selected_ips) >= max_ips:
                       break
                   if ip in current_ips and ip not in selected_ips:
                       selected_ips.append(ip)
           
           return selected_ips
           
       except Exception as e:
           self.logger.error(f"选择最优IP失败: {str(e)}")
           return list(current_scores.keys())[:max_ips]  # 发生错误时保持现有IP

   def _calculate_metrics(self, tests: Dict) -> Dict:
       """计算单次测试的指标"""
       available_tests = [t for t in tests.values() if t.get('available', False)]
       if not available_tests:
           return {'latency': float('inf'), 'loss': 100, 'available': False}
           
       return {
           'latency': statistics.mean(t['latency'] for t in available_tests),
           'loss': statistics.mean(t.get('loss', 100) for t in available_tests),
           'available': True
       }

   def get_recent_records(self, ip: str, days: int) -> List[Dict]:
       """获取指定IP最近几天的历史记录"""
       try:
           if ip not in self.history:
               return []
               
           cutoff = (datetime.now() - timedelta(days=days)).isoformat()
           return [
               record for record in self.history[ip]
               if record['timestamp'] > cutoff
           ]
           
       except Exception as e:
           self.logger.error(f"获取IP {ip} 历史记录失败: {str(e)}")
           return []
   
   def setup_logging(self):
       """设置日志"""
       log_dir = Path('logs')
       log_dir.mkdir(exist_ok=True)
       
       self.logger = logging.getLogger('IPHistoryAnalyzer')
       if not self.logger.handlers:
           formatter = logging.Formatter(
               '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
           )
           
           # 文件处理器
           fh = logging.FileHandler(
               log_dir / f'analyzer_{datetime.now():%Y%m%d}.log'
           )
           fh.setFormatter(formatter)
           
           # 控制台处理器
           ch = logging.StreamHandler()
           ch.setFormatter(formatter)
           
           self.logger.addHandler(fh)
           self.logger.addHandler(ch)
           self.logger.setLevel(logging.INFO)

   def _load_history(self) -> Dict:
        """加载IP历史记录"""
        history_file = self.results_dir / 'ip_history.json'
        if history_file.exists():
            try:
                with open(history_file) as f:
                    data = json.load(f)
                    # 确保每个IP的数据结构完整
                    for ip, record in data.items():
                        if 'http_performance' not in record:
                            record['http_performance'] = {
                                'ttfb': {},
                                'total_time': {}
                            }
                    return data
            except Exception as e:
                self.logger.error(f"加载历史记录失败: {str(e)}")
        return {}
   
   def save_history(self, test_results: List[Dict]):
        """更新和保存IP历史记录"""
        try:
            timestamp = datetime.now().isoformat()
            
            for result in test_results:
                if result['status'] != 'ok':
                    continue
                    
                ip = result['ip']
                if ip not in self.history:
                    self.history[ip] = {
                        'latency': {},
                        'http_performance': {
                            'ttfb': {},
                            'total_time': {},
                            'dns_performance': {}  # 新增DNS性能记录
                        },
                        'update_count': 0,
                        'last_update': timestamp
                    }
                
                # 更新延迟数据
                for isp, test in result['tests'].items():
                    if test.get('available', False):
                        if isp in self.history[ip]['latency']:
                            old_latency = self.history[ip]['latency'][isp]
                            new_latency = test['latency']
                            # 用加权平均更新延迟
                            self.history[ip]['latency'][isp] = new_latency * 0.7 + old_latency * 0.3
                        else:
                            self.history[ip]['latency'][isp] = test['latency']
                
                # 更新HTTP性能数据
                if 'http_test' in result and result['http_test'].get('available', False):
                    for dns_type, dns_result in result['http_test'].get('results', {}).items():
                        if dns_result.get('available', False):
                            # 更新TTFB
                            ttfb_key = f"{dns_type}"
                            if ttfb_key not in self.history[ip]['http_performance']['ttfb']:
                                self.history[ip]['http_performance']['ttfb'][ttfb_key] = dns_result['ttfb']
                            else:
                                old_ttfb = self.history[ip]['http_performance']['ttfb'][ttfb_key]
                                new_ttfb = dns_result['ttfb']
                                self.history[ip]['http_performance']['ttfb'][ttfb_key] = \
                                    new_ttfb * 0.7 + old_ttfb * 0.3
                            
                            # 更新总时间
                            time_key = f"{dns_type}"
                            if time_key not in self.history[ip]['http_performance']['total_time']:
                                self.history[ip]['http_performance']['total_time'][time_key] = \
                                    dns_result['total_time']
                            else:
                                old_time = self.history[ip]['http_performance']['total_time'][time_key]
                                new_time = dns_result['total_time']
                                self.history[ip]['http_performance']['total_time'][time_key] = \
                                    new_time * 0.7 + old_time * 0.3

                # 更新计数和时间戳
                self.history[ip]['update_count'] += 1
                self.history[ip]['last_update'] = timestamp
            
            # 保存历史记录
            with open(self.results_dir / 'ip_history.json', 'w') as f:
                json.dump(self.history, f, indent=2)
            
        except Exception as e:
            self.logger.error(f"保存历史记录失败: {str(e)}")


   def update_bad_ip(self, ip: str, result: Dict):
        """更新不良IP记录"""
        try:
            # 初始化不良IP字典
            if not hasattr(self, 'bad_ips'):
                self.bad_ips = {}
                
            if ip not in self.bad_ips:
                self.bad_ips[ip] = {
                    'first_seen': datetime.now().isoformat(),
                    'fail_count': 0,
                    'test_count': 0,
                    'last_update': datetime.now().isoformat(),
                    'recent_tests': []
                }
            
            record = self.bad_ips[ip]
            record['test_count'] += 1
            
            # 检查测试结果
            all_failed = True
            for isp_result in result['tests'].values():
                if isp_result.get('available', False):
                    all_failed = False
                    break
                    
            if all_failed:
                record['fail_count'] += 1
                
            # 更新最近测试记录
            record['recent_tests'].append({
                'timestamp': datetime.now().isoformat(),
                'tests': result['tests']
            })
            
            # 只保留最近10次测试记录
            record['recent_tests'] = record['recent_tests'][-10:]
            record['last_update'] = datetime.now().isoformat()
            
            # 保存不良IP记录
            with open(self.results_dir / 'bad_ips.json', 'w') as f:
                json.dump(self.bad_ips, f, indent=2)
                
        except Exception as e:
            self.logger.error(f"更新不良IP记录失败 {ip}: {str(e)}")
