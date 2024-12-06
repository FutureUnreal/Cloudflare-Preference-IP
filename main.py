# main.py
import json
import asyncio
import logging
import random
from typing import Dict, List
from pathlib import Path
from datetime import datetime
from src.ip_tester import IPTester
from src.core.evaluator import IPEvaluator
from src.core.recorder import IPRecorder
from src.core.analyzer import IPHistoryAnalyzer
from src.dns.dnspod import DNSPod
from src.dns.aliyun import AliDNS
from src.dns.huawei import HuaweiDNS

def setup_logging(name: str):
    """设置日志记录"""
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)
    
    # 获取日志记录器
    logger = logging.getLogger(name)
    
    # 如果已经有处理器，说明已经配置过，直接返回
    if logger.handlers:
        return logger
        
    # 设置日志格式
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 文件处理器
    file_handler = logging.FileHandler(
        log_dir / f'{name}_{datetime.now():%Y%m%d}.log'
    )
    file_handler.setFormatter(formatter)
    
    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    # 添加处理器
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logger.setLevel(logging.INFO)
    
    return logger

def load_config(config_path: str = 'config/settings.json') -> Dict:
    with open(config_path) as f:
        return json.load(f)

def generate_ip_list(config: Dict) -> List[str]:
    """生成要测试的IP列表"""
    logger = logging.getLogger('main')
    ip_list = []

    try:
        with open('config/ip_ranges.json') as f:
            ip_data = json.load(f)
        
        ip_ranges = ip_data.get('ip_ranges', [])
        skip_ips = set(ip_data.get('skip_ips', []))
        
        # 生成IP列表
        for ip_range in ip_ranges:
            prefix = ip_range.get('prefix', '')
            start = ip_range.get('start', 2)
            end = ip_range.get('end', 255)
            
            prefix_parts = prefix.split('.')
            if len(prefix_parts) == 2:  # 例如 "104.27"
                for third in range(start, end + 1):
                    for fourth in range(0, 256):
                        ip = f"{prefix}.{third}.{fourth}"
                        if ip not in skip_ips:
                            ip_list.append(ip)
            elif len(prefix_parts) == 3:  # 例如 "104.27.0"
                for fourth in range(start, end + 1):
                    ip = f"{prefix}.{fourth}"
                    if ip not in skip_ips:
                        ip_list.append(ip)

        total_ips = len(ip_list)
        logger.info(f"IP池总数: {total_ips}")
        
        # 应用抽样率或指定数量
        sample_size = None
        if 'sample_size' in config.get('test_config', {}):
            # 如果配置了具体数量，直接使用
            sample_size = config['test_config']['sample_size']
        elif 'sample_rate' in config.get('test_config', {}):
            # 如果配置了采样率，计算数量
            sample_size = max(1, int(total_ips * config['test_config']['sample_rate']))
        
        if sample_size:
            ip_list = random.sample(ip_list, min(sample_size, total_ips))
            logger.info(f"随机抽取 {len(ip_list)} 个IP进行测试")
        
        # 随机打乱顺序
        random.shuffle(ip_list)
        
        return ip_list
        
    except Exception as e:
        logger.error(f"生成IP列表失败: {str(e)}")
        return []

def init_dns_client(config: Dict):
    dns_config = config['dns']['providers']
    if dns_config['dnspod']['enabled']:
        return DNSPod(
            dns_config['dnspod']['secret_id'],
            dns_config['dnspod']['secret_key']
        )
    elif dns_config['aliyun']['enabled']:
        return AliDNS(
            dns_config['aliyun']['access_key_id'],
            dns_config['aliyun']['access_key_secret'],
            dns_config['aliyun']['region']
        )
    elif dns_config['huawei']['enabled']:
        return HuaweiDNS(
            dns_config['huawei']['ak'],
            dns_config['huawei']['sk'],
            dns_config['huawei']['region']
        )
    else:
        raise ValueError("No DNS provider enabled in config")

async def update_dns_records(dns_client, config: Dict, best_ips: Dict):
    for domain, sub_domains in config['domains'].items():
        for sub_domain, lines in sub_domains.items():
            for line in lines:
                if line in ['CM', 'CU', 'CT', 'AB']:
                    line_map = {
                        'CM': ('移动', 'MOBILE'),
                        'CU': ('联通', 'UNICOM'),
                        'CT': ('电信', 'TELECOM'),
                        'AB': ('境外', 'OVERSEAS')
                    }
                    dns_line, ip_line = line_map[line]
                    
                    if ip_line in best_ips and best_ips[ip_line]:
                        for ip in best_ips[ip_line][:config['dns']['max_records_per_line']]:
                            try:
                                dns_client.create_record(
                                    domain=domain,
                                    sub_domain=sub_domain,
                                    value=ip,
                                    record_type="A",
                                    line=dns_line,
                                    ttl=config['dns']['default_ttl']
                                )
                            except Exception as e:
                                logging.error(f"Failed to update DNS record: {str(e)}")

async def main():
   log_dir = Path('logs')
   log_dir.mkdir(exist_ok=True)
   
   logging.basicConfig(
       level=logging.INFO,
       format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
       handlers=[
           logging.FileHandler(log_dir / f'main_{datetime.now():%Y%m%d}.log'),
           logging.StreamHandler()
       ]
   )
   
   logger = logging.getLogger('main')
   logger.info("Starting IP test and DNS update process")
   
   try:
       config = load_config()
       ip_list = generate_ip_list(config)
       
       if not ip_list:
           logger.error("没有可测试的IP")
           return
           
       ip_tester = IPTester(config)
       evaluator = IPEvaluator(config)
       recorder = IPRecorder(config)
       dns_client = init_dns_client(config)
       analyzer = IPHistoryAnalyzer(config)

       current_ips = {
           'TELECOM': [],
           'UNICOM': [],
           'MOBILE': [],
           'OVERSEAS': []
       }
       
       # 获取域名配置
       domain = config['domains']['default']['domain']
       sub_domain = config['domains']['default']['subdomain']
       
       # 获取当前DNS记录
       records = dns_client.get_record(domain, 100, sub_domain, "A")
       if isinstance(records, dict) and 'records' in records:
           for record in records.get('records', []):
               line = record.get('line', '')
               if line == '移动':
                   current_ips['MOBILE'].append(record['value'])
               elif line == '联通':
                   current_ips['UNICOM'].append(record['value'])
               elif line == '电信':
                   current_ips['TELECOM'].append(record['value'])
               elif line == '境外':
                   current_ips['OVERSEAS'].append(record['value'])

       logger.info(f"开始测试 {len(ip_list)} 个IP...")
       test_results = await ip_tester.start(ip_list)
       
       logger.info("评估测试结果...")
       evaluations = evaluator.evaluate_batch(test_results)
       
       logger.info("保存测试结果...")
       recorder.save_test_results(test_results)
       
       logger.info("分析历史数据...")
       best_ips = await analyzer.analyze_and_update(
           current_ips=current_ips,
           new_test_results=evaluations
       )

       logger.info("更新DNS记录...")
       await update_dns_records(dns_client, config, best_ips)
       
       logger.info("Process completed successfully")
       
   except Exception as e:
       logger.error(f"Process failed: {str(e)}")
       raise

if __name__ == "__main__":
    asyncio.run(main())