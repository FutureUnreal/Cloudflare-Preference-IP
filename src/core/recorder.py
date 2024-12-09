import json
import logging
import statistics
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union

class IPRecorder:
    def __init__(self, config: Dict):
        self.config = config
        self.setup_logging()
        
        # 设置存储路径
        self.results_dir = Path(config.get('results_dir', 'results'))
        self.results_dir.mkdir(exist_ok=True)
        
        # 历史记录配置
        self.max_history_days = config.get('max_history_days', 30)
        self.save_interval = config.get('save_interval', 10)
        
        # 加载历史记录
        self.history = self._load_history()
        self.bad_ips = self._load_bad_ips()

    def setup_logging(self):
        """设置日志"""
        log_dir = Path('logs')
        log_dir.mkdir(exist_ok=True)
        
        self.logger = logging.getLogger('IPRecorder')
        if not self.logger.handlers:
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            
            # 文件处理器
            fh = logging.FileHandler(
                log_dir / f'recorder_{datetime.now():%Y%m%d}.log'
            )
            fh.setFormatter(formatter)
            fh.setLevel(logging.INFO)
            
            # 控制台处理器
            ch = logging.StreamHandler()
            ch.setFormatter(formatter)
            ch.setLevel(logging.INFO)
            
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
                        if 'http_tests' not in record:
                            record['http_tests'] = {}
                    return data
            except Exception as e:
                self.logger.error(f"加载历史记录失败: {str(e)}")
        return {}

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

    def _save_bad_ips(self):
        """保存不良IP记录"""
        try:
            bad_ips_file = self.results_dir / 'bad_ips.json'
            with open(bad_ips_file, 'w') as f:
                json.dump(self.bad_ips, f, indent=2)
        except Exception as e:
            self.logger.error(f"保存不良IP记录失败: {str(e)}")

    def update_bad_ip(self, ip: str, test_result: Dict):
        """更新不良IP记录"""
        try:
            if ip not in self.bad_ips:
                self.bad_ips[ip] = {
                    'first_seen': datetime.now().isoformat(),
                    'fail_count': 0,
                    'test_count': 0,
                    'recent_tests': []
                }
            
            record = self.bad_ips[ip]
            record['test_count'] += 1
            record['last_seen'] = datetime.now().isoformat()
            
            # 检查测试结果
            failed = True
            for isp_result in test_result['tests'].values():
                if isp_result.get('available', False):
                    failed = False
                    break
            
            if failed:
                record['fail_count'] += 1
            
            # 保存最近的测试结果
            record['recent_tests'].append({
                'timestamp': datetime.now().isoformat(),
                'tests': test_result['tests']
            })
            
            # 只保留最近10次测试记录
            record['recent_tests'] = record['recent_tests'][-10:]
            
            # 保存记录
            self._save_bad_ips()
            
        except Exception as e:
            self.logger.error(f"更新不良IP记录失败 {ip}: {str(e)}")

    def save_test_results(self, results: List[Dict], timestamp: str = None):
        """保存测试结果"""
        try:
            if timestamp is None:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            
            # 保存带时间戳的结果和最新结果
            result_files = [
                self.results_dir / f'test_results_{timestamp}.json',
                self.results_dir / 'test_results_latest.json'
            ]
            
            # 格式化测试结果
            formatted_results = []
            for result in results:
                if result['status'] != 'ok':
                    formatted_results.append(result)
                    continue
                
                formatted_result = {
                    'ip': result['ip'],
                    'status': result['status'],
                    'timestamp': datetime.now().isoformat(),
                    'tests': result['tests'],
                    'http_tests': {}
                }
                
                # 格式化HTTP测试结果
                if 'http_test' in result and result['http_test'].get('available', False):
                    formatted_result['http_tests'] = {
                        dns_type: {
                            'ttfb': dns_result.get('ttfb', float('inf')),
                            'total_time': dns_result.get('total_time', float('inf')),
                            'available': True
                        }
                        for dns_type, dns_result in result['http_test'].get('results', {}).items()
                        if dns_result.get('available', False)
                    }
                
                formatted_results.append(formatted_result)
            
            # 保存结果文件
            for file in result_files:
                with open(file, 'w') as f:
                    json.dump(formatted_results, f, indent=2)
            
            # 记录统计信息
            success_count = sum(1 for r in results if r['status'] == 'ok')
            self.logger.info(f"保存测试结果: 总计 {len(results)} 个IP, 成功 {success_count} 个")
            
            # 清理旧文件
            self.cleanup_old_files()
            
        except Exception as e:
            self.logger.error(f"保存测试结果失败: {str(e)}")

    def save_final_results(self, evaluations: Dict[str, List[Dict]]):
        """保存最终评估结果"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            final_file = self.results_dir / f'final_results_{timestamp}.json'
            
            result_data = {
                'timestamp': datetime.now().isoformat(),
                'evaluations': evaluations,
                'statistics': {
                    isp: {
                        'total': len(ips),
                        'avg_latency': sum(ip['latency'] for ip in ips) / len(ips) if ips else 0,
                        'min_latency': min((ip['latency'] for ip in ips), default=0),
                        'max_latency': max((ip['latency'] for ip in ips), default=0),
                        'http_stats': self._calculate_http_stats(ips)
                    }
                    for isp, ips in evaluations.items() if ips
                }
            }
            
            # 保存结果
            with open(final_file, 'w') as f:
                json.dump(result_data, f, indent=2)
            
            # 保存最新版本
            with open(self.results_dir / 'final_results_latest.json', 'w') as f:
                json.dump(result_data, f, indent=2)
                
        except Exception as e:
            self.logger.error(f"保存最终结果失败: {str(e)}")

    def _calculate_http_stats(self, ip_results: List[Dict]) -> Dict:
        """计算HTTP测试统计信息"""
        stats = {
            'ALIYUN': {'ttfb': [], 'total_time': []},
            'BAIDU': {'ttfb': [], 'total_time': []},
            'GOOGLE': {'ttfb': [], 'total_time': []}
        }
        
        for ip in ip_results:
            if 'http_tests' in ip:
                for dns_type, result in ip['http_tests'].items():
                    if dns_type in stats and result.get('available', False):
                        stats[dns_type]['ttfb'].append(result['ttfb'])
                        stats[dns_type]['total_time'].append(result['total_time'])
        
        # 计算平均值和最值
        for dns_type in stats:
            if stats[dns_type]['ttfb']:
                stats[dns_type]['avg_ttfb'] = statistics.mean(stats[dns_type]['ttfb'])
                stats[dns_type]['min_ttfb'] = min(stats[dns_type]['ttfb'])
                stats[dns_type]['max_ttfb'] = max(stats[dns_type]['ttfb'])
            
            if stats[dns_type]['total_time']:
                stats[dns_type]['avg_total_time'] = statistics.mean(stats[dns_type]['total_time'])
                stats[dns_type]['min_total_time'] = min(stats[dns_type]['total_time'])
                stats[dns_type]['max_total_time'] = max(stats[dns_type]['total_time'])
        
        return stats

    def cleanup_old_files(self):
        """清理旧的测试结果文件"""
        try:
            cutoff = datetime.now() - timedelta(days=self.max_history_days)
            patterns = [
                'test_results_*.json',
                'final_results_*.json',
                'ip_pools_*.json'
            ]
            
            for pattern in patterns:
                for file in self.results_dir.glob(pattern):
                    if ('latest' not in file.name and 
                        datetime.fromtimestamp(file.stat().st_mtime) < cutoff):
                        file.unlink()
                        self.logger.info(f"已删除旧文件: {file.name}")
                        
        except Exception as e:
            self.logger.error(f"清理旧文件失败: {str(e)}")

    def get_ip_history(self, ip: str, days: Optional[int] = None) -> List[Dict]:
        """获取指定IP的历史记录"""
        try:
            if ip not in self.history:
                return []
            
            records = self.history[ip]
            if days is not None:
                cutoff = (datetime.now() - timedelta(days=days)).isoformat()
                if isinstance(records, list):
                    records = [r for r in records if r['timestamp'] > cutoff]
                elif isinstance(records, dict) and 'last_update' in records:
                    if records['last_update'] < cutoff:
                        return []
            
            return records
            
        except Exception as e:
            self.logger.error(f"获取IP历史记录失败 {ip}: {str(e)}")
            return []

    def is_bad_ip(self, ip: str) -> bool:
        """检查IP是否为不良IP"""
        try:
            if ip not in self.bad_ips:
                return False
            
            record = self.bad_ips[ip]
            if record['test_count'] < self.config.get('min_tests_for_bad_ip', 5):
                return False
            
            fail_rate = record['fail_count'] / record['test_count']
            return fail_rate > self.config.get('bad_ip_threshold', 0.8)
            
        except Exception as e:
            self.logger.error(f"检查不良IP失败 {ip}: {str(e)}")
            return False

    def get_statistics(self) -> Dict:
        """获取统计信息"""
        try:
            stats = {
                'total_ips': len(self.history),
                'bad_ips': len(self.bad_ips),
                'recent_tests': 0,
                'success_rate': 0,
                'http_performance': {
                    'ALIYUN': {'success': 0, 'total': 0},
                    'BAIDU': {'success': 0, 'total': 0},
                    'GOOGLE': {'success': 0, 'total': 0}
                }
            }
            
            # 计算最近24小时的测试统计
            cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
            success_count = 0
            total_count = 0
            
            for ip, records in self.history.items():
                if isinstance(records, list):
                    for record in records:
                        if record['timestamp'] > cutoff:
                            total_count += 1
                            
                            # 检查ping测试成功率
                            if any(test.get('available', False) for test in record['tests'].values()):
                                success_count += 1
                            
                            # 检查HTTP测试成功率
                            if 'http_tests' in record:
                                for dns_type, result in record['http_tests'].items():
                                    if dns_type in stats['http_performance']:
                                        stats['http_performance'][dns_type]['total'] += 1
                                        if result.get('available', False):
                                            stats['http_performance'][dns_type]['success'] += 1
            
            stats['recent_tests'] = total_count
            if total_count > 0:
                stats['success_rate'] = (success_count / total_count) * 100
                
                # 计算每个DNS的成功率
                for dns_type in stats['http_performance']:
                    dns_stats = stats['http_performance'][dns_type]
                    if dns_stats['total'] > 0:
                        dns_stats['success_rate'] = (dns_stats['success'] / dns_stats['total']) * 100
            
            return stats
            
        except Exception as e:
            self.logger.error(f"获取统计信息失败: {str(e)}")
            return {}