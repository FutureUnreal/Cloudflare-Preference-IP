import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional
from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkdns.v2 import *
from huaweicloudsdkdns.v2.region.dns_region import DnsRegion

class HuaweiDNS:
    def __init__(self, ak: str, sk: str, region: str = 'cn-east-3'):
        self.AK = ak  
        self.SK = sk
        self.region = region
        
        # 初始化日志
        self.setup_logging()
        
        # 初始化客户端
        self.credentials = BasicCredentials(ak, sk)
        self.client = DnsClient.new_builder() \
            .with_credentials(self.credentials) \
            .with_region(DnsRegion.value_of(region)) \
            .build()
            
        # 缓存zone_id
        self.zone_map = self._get_zones()

    def setup_logging(self):
        """设置日志"""
        self.logger = logging.getLogger('HuaweiDNS')
        if not self.logger.handlers:
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            # 控制台处理器
            ch = logging.StreamHandler()
            ch.setFormatter(formatter)
            ch.setLevel(logging.INFO)
            self.logger.addHandler(ch)
            self.logger.setLevel(logging.INFO)

    def _get_zones(self) -> Dict[str, str]:
        """获取所有域名的zone_id映射"""
        try:
            request = ListPublicZonesRequest()
            response = self.client.list_public_zones(request)
            result = json.loads(str(response))
            
            return {
                zone['name']: zone['id']
                for zone in result.get('zones', [])
            }
            
        except Exception as e:
            self.logger.error(f"获取zone列表失败: {str(e)}")
            return {}

    def get_record(self, domain: str, length: int, sub_domain: str, record_type: str) -> Dict:
        """获取解析记录"""
        try:
            request = ListRecordSetsWithLineRequest()
            request.limit = length
            request.type = record_type
            request.name = f"{sub_domain}.{domain}." if sub_domain != '@' else f"{domain}."

            response = self.client.list_record_sets_with_line(request)
            data = json.loads(str(response))
            
            # 格式化返回结果
            result = {"data": {"records": []}}
            for record in data['recordsets']:
                if ((sub_domain == '@' and f"{domain}." == record['name']) or 
                    (f"{sub_domain}.{domain}." == record['name'])):
                    # 格式化记录
                    formatted_record = {
                        'id': record['id'],
                        'name': record['name'],
                        'type': record['type'],
                        'line': self._line_format(record['line']),
                        'value': record['records'][0],
                        'ttl': record['ttl']
                    }
                    result['data']['records'].append(formatted_record)
            
            return result
            
        except Exception as e:
            self.logger.error(f"获取记录失败: {str(e)}")
            return {"data": {"records": []}}

    def create_record(self, domain: str, sub_domain: str, value: str, 
                     record_type: str = "A", line: str = "默认", ttl: int = 600) -> Dict:
        """创建解析记录"""
        try:
            zone_id = self.zone_map.get(domain + '.')
            if not zone_id:
                raise ValueError(f"未找到域名 {domain} 的zone_id")

            request = CreateRecordSetWithLineRequest()
            request.zone_id = zone_id
            
            # 处理子域名
            name = f"{sub_domain}.{domain}." if sub_domain != '@' else f"{domain}."
            
            # 创建记录
            body = CreateRecordSetWithLineReq(
                name=name,
                type=record_type,
                ttl=ttl,
                records=[value],
                line=self._line_format(line)
            )
            request.body = body

            response = self.client.create_record_set_with_line(request)
            return json.loads(str(response))
            
        except Exception as e:
            self.logger.error(f"创建记录失败: {str(e)}")
            raise

    def update_record(self, domain: str, record_id: str, sub_domain: str,
                     value: str, record_type: str = "A", line: str = "默认", ttl: int = 600) -> Dict:
        """更新解析记录"""
        try:
            zone_id = self.zone_map.get(domain + '.')
            if not zone_id:
                raise ValueError(f"未找到域名 {domain} 的zone_id")

            request = UpdateRecordSetRequest()
            request.zone_id = zone_id
            request.recordset_id = record_id
            
            name = f"{sub_domain}.{domain}." if sub_domain != '@' else f"{domain}."
            
            body = UpdateRecordSetReq(
                name=name,
                type=record_type,
                ttl=ttl,
                records=[value]
            )
            request.body = body

            response = self.client.update_record_set(request)
            return json.loads(str(response))
            
        except Exception as e:
            self.logger.error(f"更新记录失败: {str(e)}")
            raise

    def delete_record(self, domain: str, record_id: str) -> Dict:
        """删除解析记录"""
        try:
            zone_id = self.zone_map.get(domain + '.')
            if not zone_id:
                raise ValueError(f"未找到域名 {domain} 的zone_id")

            request = DeleteRecordSetsRequest()
            request.zone_id = zone_id
            request.recordset_id = record_id

            response = self.client.delete_record_sets(request)
            return json.loads(str(response))
            
        except Exception as e:
            self.logger.error(f"删除记录失败: {str(e)}")
            raise

    def _line_format(self, line: str) -> str:
        """线路格式转换"""
        line_map = {
            "默认": "default_view",
            "电信": "Dianxin",
            "联通": "Liantong",
            "移动": "Yidong",
            "境外": "Abroad",
            "default_view": "默认",
            "Dianxin": "电信",
            "Liantong": "联通",
            "Yidong": "移动",
            "Abroad": "境外"
        }
        return line_map.get(line, line)