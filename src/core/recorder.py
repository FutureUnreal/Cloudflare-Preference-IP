#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import logging
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
                    return json.load(f)
            except Exception as e:
                self.logger.error(f"加载历史记录失败: {str(e)}")
        return {}

    def _save_history(self):
        """保存IP历史记录"""
        try:
            history_file = self.results_dir / 'ip_history.json'
            with open(history_file, 'w') as f:
                json.dump(self.history, f, indent=2)
        except Exception as e:
            self.logger.error(f"保存历史记录失败: {str(e)}")

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

    def update_ip_history(self, ip: str, test_result: Dict):
        """更新IP的历史记录"""
        try:
            if ip not in self.history:
                self.history[ip] = []
            
            # 清理过期记录
            cutoff = (datetime.now() - timedelta(days=self.max_history_days)).isoformat()
            self.history[ip] = [
                record for record in self.history[ip]
                if record['timestamp'] > cutoff
            ]
            
            # 添加新记录
            new_record = {
                'timestamp': datetime.now().isoformat(),
                'tests': test_result['tests']
            }
            
            self.history[ip].append(new_record)
            
        except Exception as e:
            self.logger.error(f"更新历史记录失败 {ip}: {str(e)}")

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
            
        except Exception as e:
            self.logger.error(f"更新不良IP记录失败 {ip}: {str(e)}")

    def save_test_results(self, results: List[Dict]):
        """保存测试结果并更新历史"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            
            # 保存原始测试结果
            results_file = self.results_dir / f'test_results_{timestamp}.json'
            latest_file = self.results_dir / 'test_results_latest.json'
            
            for file in [results_file, latest_file]:
                with open(file, 'w') as f:
                    json.dump(results, f, indent=2)
            
            # 更新并保存历史数据
            self.save_history(results)
            
            # 记录成功数量
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
                        'max_latency': max((ip['latency'] for ip in ips), default=0)
                    }
                    for isp, ips in evaluations.items() if ips
                }
            }
            
            with open(final_file, 'w') as f:
                json.dump(result_data, f, indent=2)
                
            # 保存最新版本
            with open(self.results_dir / 'final_results_latest.json', 'w') as f:
                json.dump(result_data, f, indent=2)
                
        except Exception as e:
            self.logger.error(f"保存最终结果失败: {str(e)}")

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
                records = [r for r in records if r['timestamp'] > cutoff]
            
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
                'success_rate': 0
            }
            
            # 计算最近24小时的测试统计
            cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
            success_count = 0
            total_count = 0
            
            for ip, records in self.history.items():
                recent_records = [r for r in records if r['timestamp'] > cutoff]
                total_count += len(recent_records)
                
                for record in recent_records:
                    if any(test.get('available', False) for test in record['tests'].values()):
                        success_count += 1
            
            stats['recent_tests'] = total_count
            if total_count > 0:
                stats['success_rate'] = (success_count / total_count) * 100
                
            return stats
            
        except Exception as e:
            self.logger.error(f"获取统计信息失败: {str(e)}")
            return {}