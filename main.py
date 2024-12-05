import json
import asyncio
import logging
from typing import Dict, List
from pathlib import Path
from datetime import datetime
from src.ip_tester import IPTester
from src.core.evaluator import IPEvaluator
from src.core.recorder import IPRecorder
from src.dns.dnspod import DNSPod
from src.dns.aliyun import AliDNS
from src.dns.huawei import HuaweiDNS

def setup_logging():
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
    return logging.getLogger('main')

def load_config(config_path: str = 'config/settings.json') -> Dict:
    with open(config_path) as f:
        return json.load(f)

def load_ip_ranges(ranges_path: str = 'config/ip_ranges.json') -> List[str]:
    with open(ranges_path) as f:
        data = json.load(f)
    
    ip_list = []
    skip_ips = set(data.get('skip_ips', []))
    
    for range_info in data['ip_ranges']:
        prefix = range_info['prefix']
        for i in range(range_info['start'], range_info['end'] + 1):
            ip = f"{prefix}.{i}"
            if ip not in skip_ips:
                ip_list.append(ip)
    
    return ip_list

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
    logger = setup_logging()
    logger.info("Starting IP test and DNS update process")
    
    try:
        # 加载配置
        config = load_config()
        ip_list = load_ip_ranges()
        
        # 初始化组件
        ip_tester = IPTester(config)
        evaluator = IPEvaluator(config)
        recorder = IPRecorder(config)
        dns_client = init_dns_client(config)
        
        # 测试IP
        logger.info(f"Testing {len(ip_list)} IPs...")
        test_results = ip_tester.start(ip_list)
        
        # 评估结果
        logger.info("Evaluating results...")
        evaluations = evaluator.evaluate_batch(test_results)
        
        # 记录结果
        logger.info("Saving results...")
        recorder.save_test_results(test_results)
        
        # 获取最佳IP
        best_ips = evaluator.get_best_ips(
            evaluations, 
            limit=config['dns']['max_records_per_line']
        )
        
        # 更新DNS记录
        logger.info("Updating DNS records...")
        await update_dns_records(dns_client, config, best_ips)
        
        logger.info("Process completed successfully")
        
    except Exception as e:
        logger.error(f"Process failed: {str(e)}")
        raise

if __name__ == "__main__":
    asyncio.run(main())