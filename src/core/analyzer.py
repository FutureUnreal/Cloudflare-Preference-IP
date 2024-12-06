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
       self.history = self._load_history()
       
       # 分析参数
       self.analysis_days = config.get('analysis_days', 7)  
       self.min_samples = config.get('min_samples', 10)    
       self.latency_volatility_threshold = config.get('latency_volatility', 0.3)
       self.availability_threshold = config.get('availability_threshold', 0.9)

   async def analyze_and_update(self, current_ips: Dict[str, List[str]], 
                              new_test_results: Dict[str, List[Dict]]) -> Dict[str, List[str]]:
       """分析历史数据并自动更新IP列表"""
       try:
           optimized_ips = {}
           
           for isp, ips in current_ips.items():
               # 分析当前使用的IP
               current_ip_scores = await self._analyze_ip_batch(ips)
               
               # 分析新测试的IP
               new_ip_scores = await self._analyze_ip_batch([r['ip'] for r in new_test_results[isp]])
               
               # 自动选择最优IP组合
               optimized_ips[isp] = self._select_optimal_ips(
                   current_ip_scores,
                   new_ip_scores,
                   self.config['dns']['max_records_per_line']
               )
           
           return optimized_ips
           
       except Exception as e:
           self.logger.error(f"IP优化失败: {str(e)}")
           return current_ips  # 发生错误时保持现有IP不变

   async def _analyze_ip_batch(self, ips: List[str]) -> Dict[str, float]:
       """批量分析IP历史表现"""
       scores = {}
       
       for ip in ips:
           scores[ip] = await self._calculate_historical_score(ip)
           
       return scores

   async def _calculate_historical_score(self, ip: str) -> float:
       """计算IP的历史综合得分"""
       try:
           records = self.get_recent_records(ip, self.analysis_days)
           if len(records) < self.min_samples:
               return 0  # 样本不足
               
           # 计算关键指标
           latencies = []
           loss_rates = []
           availability_count = 0
           
           for record in records:
               metrics = self._calculate_metrics(record['tests'])
               if metrics['available']:
                   latencies.append(metrics['latency'])
                   loss_rates.append(metrics['loss'])
                   availability_count += 1
           
           if not latencies:
               return 0
               
           # 计算指标
           avg_latency = statistics.mean(latencies)
           latency_volatility = statistics.stdev(latencies) / avg_latency if len(latencies) > 1 else 1
           avg_loss = statistics.mean(loss_rates)
           availability = availability_count / len(records)
           
           # 综合评分
           if (latency_volatility > self.latency_volatility_threshold or
               availability < self.availability_threshold):
               return 0  # 不稳定或可用性差
           
           # 计算最终得分
           score = (
               (1000 - min(1000, avg_latency)) * 0.4 +  # 延迟得分
               (100 - min(100, avg_loss)) * 0.3 +      # 丢包得分
               (availability * 100) * 0.3              # 可用性得分
           )
           
           return score
           
       except Exception as e:
           self.logger.error(f"计算IP {ip} 历史得分失败: {str(e)}")
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
