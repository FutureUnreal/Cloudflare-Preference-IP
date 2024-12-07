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
       
       # 分析参数
       self.analysis_days = config.get('analysis_days', 7)  
       self.min_samples = config.get('min_samples', 10)    
       self.latency_volatility_threshold = config.get('latency_volatility', 0.3)
       self.availability_threshold = config.get('availability_threshold', 0.9)


   async def analyze_and_update(self, current_ips: Dict[str, List[str]], 
                         new_test_results: Dict[str, List[Dict]]) -> Dict[str, List[str]]:
        """分析并选择最优IP组合"""
        try:
            self.logger.info("开始分析IP...")
            self.logger.info(f"历史记录中的IP数量: {len(self.history)}")
            
            optimized_ips = {
                'TELECOM': [],
                'UNICOM': [],
                'MOBILE': [],
                'OVERSEAS': [],
                'DEFAULT': []
            }

            for isp in optimized_ips.keys():
                self.logger.info(f"\n处理 {isp} 线路...")
                
                # 分别获取当前IP和新IP的得分
                current_ip_scores = {}
                if isp in current_ips:
                    self.logger.info(f"{isp} 当前使用的IP列表: {current_ips[isp]}")
                    for ip in current_ips[isp]:
                        self.logger.info(f"计算IP {ip} 的历史得分")
                        # 这里修改为传入 isp 参数
                        score = await self._calculate_historical_score(ip, isp)
                        self.logger.info(f"IP {ip} 的历史得分: {score}")
                        if score > 0:
                            current_ip_scores[ip] = score
                        else:
                            self.logger.info(f"IP {ip} 得分为0，不计入当前IP得分")
                            
                self.logger.info(f"{isp} 当前IP得分汇总: {current_ip_scores}")

                # 处理新测试的IP
                new_ip_scores = {}
                if isp in new_test_results:
                    for result in new_test_results[isp]:
                        ip = result['ip']
                        latency = result['latency']
                        # 使用延迟的倒数作为得分
                        score = 1000 / latency if latency > 0 else 0
                        if score > 0:
                            new_ip_scores[ip] = score
                            self.logger.info(f"新测试 IP {ip} 得分: {score} (延迟: {latency}ms)")
                    self.logger.info(f"{isp} 新测试IP得分汇总: {new_ip_scores}")

                # 合并得分并排序
                all_scores = {**current_ip_scores, **new_ip_scores}
                sorted_ips = sorted(
                    all_scores.items(),
                    key=lambda x: (-x[1], x[0])  # 按得分降序，IP升序
                )

                # 选择最优IP
                max_records = self.config['dns']['max_records_per_line']
                selected_ips = [ip for ip, _ in sorted_ips[:max_records]]
                
                if selected_ips:
                    optimized_ips[isp] = selected_ips
                    self.logger.info(f"{isp} 最终选择的IP: {selected_ips}")
                else:
                    self.logger.warning(f"{isp} 没有合格的IP")

            self.logger.info(f"IP分析完成，最终选择: {optimized_ips}")
            return optimized_ips

        except Exception as e:
            self.logger.error(f"IP分析失败: {str(e)}", exc_info=True)
            return current_ips

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
            if isp not in record['latency']:
                self.logger.info(f"IP {ip} 没有 {isp} 线路的延迟记录")
                return 0

            latency = record['latency'][isp]
            last_update = datetime.fromisoformat(record['last_update'])
            update_count = record['update_count']
            
            # 检查记录是否过期
            days_old = (datetime.now() - last_update).days
            if days_old > self.analysis_days:
                self.logger.info(f"IP {ip} 的记录已过期 ({days_old} 天)")
                return 0

            # 计算得分
            latency_score = 1000 / latency if latency > 0 else 0
            stability_bonus = min(100, update_count * 10)
            final_score = latency_score + stability_bonus
            
            self.logger.info(f"IP {ip} {isp} 线路得分计算:")
            self.logger.info(f"  延迟: {latency}ms")
            self.logger.info(f"  延迟得分: {latency_score}")
            self.logger.info(f"  稳定性加分: {stability_bonus}")
            self.logger.info(f"  最终得分: {final_score}")
            
            return final_score

        except Exception as e:
            self.logger.error(f"计算IP {ip} 历史得分时出错: {str(e)}")
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
                   return json.load(f)
           except Exception as e:
               self.logger.error(f"加载历史记录失败: {str(e)}")
       return {}
   
   def save_history(self, test_results: List[Dict]):
        """保存新的测试结果到历史记录"""
        try:
            timestamp = datetime.now().isoformat()
            
            for result in test_results:
                ip = result['ip']
                if ip not in self.history:
                    self.history[ip] = {
                        'latency': {},
                        'update_count': 0,
                        'last_update': timestamp
                    }
                
                # 更新各线路的延迟
                for isp, test in result['tests'].items():
                    if test.get('available', False):
                        # 如果已有记录，做加权平均
                        if isp in self.history[ip]['latency']:
                            old_latency = self.history[ip]['latency'][isp]
                            new_latency = test['latency']
                            # 新数据权重0.7，旧数据权重0.3
                            weighted_latency = new_latency * 0.7 + old_latency * 0.3
                            self.history[ip]['latency'][isp] = weighted_latency
                        else:
                            self.history[ip]['latency'][isp] = test['latency']
                            
                # 计算默认线路的延迟（所有可用线路的平均值）
                available_latencies = [
                    latency for isp, latency in self.history[ip]['latency'].items()
                    if isp != 'DEFAULT'
                ]
                if available_latencies:
                    self.history[ip]['latency']['DEFAULT'] = statistics.mean(available_latencies)
                    
                # 更新计数和时间戳
                self.history[ip]['update_count'] += 1
                self.history[ip]['last_update'] = timestamp
                
            # 保存到文件
            self.results_dir.mkdir(exist_ok=True)
            with open(self.results_dir / 'ip_history.json', 'w') as f:
                json.dump(self.history, f, indent=2)
                
        except Exception as e:
            self.logger.error(f"保存历史记录失败: {str(e)}")
