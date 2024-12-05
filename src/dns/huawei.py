import json
import logging
from typing import Dict, Optional
from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkdns.v2 import *
from huaweicloudsdkdns.v2.region.dns_region import DnsRegion

class HuaweiDNS:
    LINE_MAP = {
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

    def __init__(self, ak: str, sk: str, region: str = 'cn-east-3'):
        self.logger = logging.getLogger('HuaweiDNS')
        self.credentials = BasicCredentials(ak, sk)
        self.client = DnsClient.new_builder() \
            .with_credentials(self.credentials) \
            .with_region(DnsRegion.value_of(region)) \
            .build()
        self.zone_map = {}

    def _get_zone_id(self, domain: str) -> str:
        """获取域名的zone_id"""
        try:
            if domain not in self.zone_map:
                request = ListPublicZonesRequest()
                response = self.client.list_public_zones(request)
                result = json.loads(str(response))
                
                for zone in result.get('zones', []):
                    if zone['name'] == domain + '.':
                        self.zone_map[domain] = zone['id']
                        break

            return self.zone_map.get(domain)
        except Exception as e:
            self.logger.error(f"Failed to get zone_id: {str(e)}")
            raise

    def get_record(self, domain: str, length: int, sub_domain: str, record_type: str) -> Dict:
        """获取域名解析记录"""
        try:
            request = ListRecordSetsWithLineRequest()
            request.limit = length
            request.type = record_type
            request.name = f"{sub_domain}.{domain}." if sub_domain != '@' else f"{domain}."

            response = self.client.list_record_sets_with_line(request)
            return json.loads(str(response))
        except Exception as e:
            self.logger.error(f"Failed to get records: {str(e)}")
            raise

    def create_record(self, domain: str, sub_domain: str, value: str, 
                     record_type: str = "A", line: str = "默认", ttl: int = 600) -> Dict:
        """创建域名解析记录"""
        try:
            zone_id = self._get_zone_id(domain)
            if not zone_id:
                raise ValueError(f"Zone id not found for domain {domain}")

            request = CreateRecordSetWithLineRequest()
            request.zone_id = zone_id
            name = f"{sub_domain}.{domain}." if sub_domain != '@' else f"{domain}."
            
            body = CreateRecordSetWithLineReq(
                name=name,
                type=record_type,
                ttl=ttl,
                records=[value],
                line=self.LINE_MAP.get(line, line)
            )
            request.body = body

            response = self.client.create_record_set_with_line(request)
            return json.loads(str(response))
        except Exception as e:
            self.logger.error(f"Failed to create record: {str(e)}")
            raise

    def update_record(self, domain: str, record_id: str, sub_domain: str, 
                     value: str, record_type: str = "A", line: str = "默认", ttl: int = 600) -> Dict:
        """更新域名解析记录"""
        try:
            zone_id = self._get_zone_id(domain)
            if not zone_id:
                raise ValueError(f"Zone id not found for domain {domain}")

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
            self.logger.error(f"Failed to update record: {str(e)}")
            raise

    def delete_record(self, domain: str, record_id: str) -> Dict:
        """删除域名解析记录"""
        try:
            zone_id = self._get_zone_id(domain)
            if not zone_id:
                raise ValueError(f"Zone id not found for domain {domain}")

            request = DeleteRecordSetsRequest()
            request.zone_id = zone_id
            request.recordset_id = record_id

            response = self.client.delete_record_sets(request)
            return json.loads(str(response))
        except Exception as e:
            self.logger.error(f"Failed to delete record: {str(e)}")
            raise