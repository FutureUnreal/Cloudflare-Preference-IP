# main.py
import json
import asyncio
import logging
import random
from typing import Dict, List
from pathlib import Path
from datetime import datetime
from src.ip_tester import IPTester
from src.ip_validator import IPValidator
from src.core.evaluator import IPEvaluator
from src.core.recorder import IPRecorder
from src.core.analyzer import IPHistoryAnalyzer
from src.dns.dnspod import DNSPod
from src.dns.aliyun import AliDNS
from src.dns.huawei import HuaweiDNS

def main(self):
    """设置日志"""
    self.logger = logging.getLogger('IPEvaluator')
    
    # 检查是否已经配置过
    if not self.logger.handlers:
        log_dir = Path('logs')
        log_dir.mkdir(exist_ok=True)
        
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # 文件处理器
        fh = logging.FileHandler(
            log_dir / f'evaluator_{datetime.now():%Y%m%d}.log'
        )
        fh.setFormatter(formatter)
        
        # 控制台处理器
        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        
        self.logger.addHandler(fh)
        self.logger.addHandler(ch)
        self.logger.setLevel(logging.INFO)

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
    logger = logging.getLogger('main')
    logger.info(f"Current best IPs: {best_ips}")
    
    domain = config['domains']['default']['domain']
    sub_domain = config['domains']['default']['subdomain']
    
    try:
        # 1. 获取当前DNS记录
        current_records = dns_client.get_record(domain, 100, sub_domain, "A")
        current_ips = {
            'TELECOM': [],
            'UNICOM': [],
            'MOBILE': [],
            'OVERSEAS': [],
            'DEFAULT': []
        }
        
        ip_record_map = {}
        
        if 'records' in current_records.get('data', {}):
            for record in current_records['data']['records']:
                if record['Type'] == 'A':
                    ip = record['value']
                    line = record['line']
                    ip_record_map[ip] = {
                        'id': record['id'],
                        'line': line
                    }
                    
                    if line == '电信':
                        current_ips['TELECOM'].append(ip)
                    elif line == '联通':
                        current_ips['UNICOM'].append(ip)
                    elif line == '移动':
                        current_ips['MOBILE'].append(ip)
                    elif line == '境外':
                        current_ips['OVERSEAS'].append(ip)
                    elif line == '默认':
                        current_ips['DEFAULT'].append(ip)

        logger.info(f"Current DNS records: {current_ips}")

        # 2. 评估所有IP
        analyzer = IPHistoryAnalyzer(config)
        final_ips = {
            'TELECOM': [],
            'UNICOM': [],
            'MOBILE': [],
            'OVERSEAS': [],
            'DEFAULT': []
        }

        for isp in ['TELECOM', 'UNICOM', 'MOBILE', 'OVERSEAS']:
            # 合并当前IP和新测试IP
            candidate_ips = set()
            if isp in current_ips:
                candidate_ips.update(current_ips[isp])
            if isp in best_ips:
                candidate_ips.update(best_ips[isp])
            
            # 计算每个IP的得分
            ip_scores = {}
            for ip in candidate_ips:
                score = await analyzer._calculate_historical_score(ip, isp)
                if score > 0:
                    ip_scores[ip] = score
            
            # 选择最高分的IP
            max_records = config['dns']['max_records_per_line'].get(isp, 1)
            sorted_ips = sorted(ip_scores.items(), key=lambda x: (-x[1], x[0]))
            final_ips[isp] = [ip for ip, score in sorted_ips[:max_records]]
            
            logger.info(f"{isp} final selection: {final_ips[isp]}")
            
        # 为DEFAULT线路选择综合表现最好的IP
        default_scores = {}
        for isp, ips in final_ips.items():
            if ips:  # 从每个线路选择最好的IP
                ip = ips[0]
                score = await analyzer._calculate_historical_score(ip, 'DEFAULT')
                if score > 0:
                    default_scores[ip] = score
        
        if default_scores:
            best_default_ip = max(default_scores.items(), key=lambda x: x[1])[0]
            final_ips['DEFAULT'] = [best_default_ip]

        # 3. 更新DNS记录
        if not any(ips for ips in final_ips.values()):
            logger.warning("没有找到合格的IP，保留现有DNS记录")
            return
            
        # 删除不再使用的记录
        for ip, record_info in ip_record_map.items():
            keep_ip = False
            for isp_ips in final_ips.values():
                if ip in isp_ips:
                    keep_ip = True
                    break
            
            if not keep_ip:
                try:
                    logger.info(f"删除记录: {record_info['id']} ({ip}, {record_info['line']})")
                    dns_client.delete_record(domain, record_info['id'])
                except Exception as e:
                    logger.error(f"删除记录失败 {record_info['id']}: {str(e)}")
        
        # 添加或保留记录
        line_map = {
            'TELECOM': '电信',
            'UNICOM': '联通',
            'MOBILE': '移动',
            'OVERSEAS': '境外',
            'DEFAULT': '默认'
        }
        
        for isp, ips in final_ips.items():
            dns_line = line_map.get(isp)
            if dns_line and ips:
                for ip in ips:
                    if ip in ip_record_map:
                        logger.info(f"保留现有记录: {ip} ({dns_line})")
                        continue
                        
                    try:
                        result = dns_client.create_record(
                            domain=domain,
                            sub_domain=sub_domain,
                            value=ip,
                            record_type="A",
                            line=dns_line,
                            ttl=config['dns']['default_ttl']
                        )
                        logger.info(f"添加新记录: {ip} ({dns_line})")
                    except Exception as e:
                        logger.error(f"添加记录失败: {str(e)}")
        
    except Exception as e:
        logger.error(f"更新DNS记录失败: {str(e)}")
        raise

async def main():
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_dir / f'main_{datetime.now():%Y%m%d}.log'),
            logging.StreamHandler()
        ]
    )
    
    logger = logging.getLogger('main')
    logger.info("开始IP测试和DNS更新流程")
    
    try:
        # 加载配置
        config = load_config()
        logger.info("加载配置...")
        logger.info(f"域名配置: {config['domains']}")
        
        domain = config['domains']['default']['domain']
        sub_domain = config['domains']['default']['subdomain']
        logger.info(f"即将更新域名: {domain}, 子域名: {sub_domain}")
        
        # 初始化DNS客户端并测试连接
        dns_client = init_dns_client(config)
        test_result = dns_client.get_record(domain, 1, "", "A")
        logger.info(f"DNS连接测试结果: {test_result}")
        
        # 生成IP列表
        ip_list = generate_ip_list(config)
        if not ip_list:
            logger.error("没有可测试的IP")
            return
            
        # 初始化各个组件
        ip_tester = IPTester(config)
        evaluator = IPEvaluator(config)
        recorder = IPRecorder(config)
        analyzer = IPHistoryAnalyzer(config)
        validator = IPValidator(config)  # 新增验证器
        
        # 获取当前DNS记录中的IP
        current_ips = {
            'TELECOM': [],
            'UNICOM': [], 
            'MOBILE': [],
            'OVERSEAS': [],
            'DEFAULT': []
        }
        
        # 获取当前DNS记录
        records = dns_client.get_record(domain, 100, sub_domain, "A")

        if isinstance(records, dict) and 'records' in records.get('data', {}):
            for record in records['data']['records']:
                line = record.get('line', '')
                value = record.get('value', '')
                
                # 处理Unicode编码的线路名称
                if line == '移动' or line == '\u79fb\u52a8':
                    current_ips['MOBILE'].append(value)
                elif line == '联通' or line == '\u8054\u901a':
                    current_ips['UNICOM'].append(value)
                elif line == '电信' or line == '\u7535\u4fe1':
                    current_ips['TELECOM'].append(value)
                elif line == '境外' or line == '\u5883\u5916':
                    current_ips['OVERSEAS'].append(value)
                elif line == '默认' or line == '\u9ed8\u8ba4':
                    current_ips['DEFAULT'].append(value)

        logger.info(f"当前DNS记录中的IP: {current_ips}")

        # 测试新的IP
        logger.info(f"开始测试 {len(ip_list)} 个IP...")
        test_results = await ip_tester.start(ip_list)
        
        # 评估测试结果
        logger.info("评估测试结果...")
        evaluations = evaluator.evaluate_batch(test_results)
        logger.info("初步评估结果:")
        for isp, ips in evaluations.items():
            logger.info(f"{isp}: {len(ips)} 个IP")
            for ip_data in ips:
                logger.info(f"  IP: {ip_data['ip']}, 延迟: {ip_data['latency']}ms")
        
        # 多节点验证
        logger.info("开始多节点验证...")
        validated_evaluations = await validator.batch_validate(evaluations)
        for isp, ips in validated_evaluations.items():
            logger.info(f"{isp}: {len(ips)} 个IP")
            for ip_data in ips:
                logger.info(f"  IP: {ip_data['ip']}, 延迟: {ip_data['latency']}ms")
        
        logger.info("保存测试结果...")
        recorder.save_test_results(test_results, timestamp)
        analyzer.save_history(test_results)
        
        # 分析历史数据
        logger.info("分析历史数据...")
        best_ips = await analyzer.analyze_and_update(
            current_ips=current_ips,
            new_test_results=validated_evaluations  # 使用验证后的结果
        )
        
        logger.info("更新DNS记录...")
        # 更新DNS记录
        await update_dns_records(dns_client, config, best_ips)

        logger.info("所有流程已成功完成")

        try:
            # 清理中间结果文件和临时文件
            for file in Path('results').glob('test_results_intermediate_*.json'):
                file.unlink()
                logger.info(f"已删除中间文件: {file.name}")
                
            results_dir = Path(config.get('results_dir', 'results'))
            temp_file = results_dir / f'test_results_{timestamp}.json'
            if temp_file.exists():
                temp_file.unlink()
                logger.info(f"已删除临时文件: {temp_file.name}")
        except Exception as e:
            logger.error(f"清理临时文件失败: {str(e)}")
        
    except Exception as e:
        logger.error(f"流程执行失败: {str(e)}")
        raise

if __name__ == "__main__":
    asyncio.run(main())