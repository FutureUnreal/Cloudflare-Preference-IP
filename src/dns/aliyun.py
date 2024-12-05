import json
import logging
from typing import Dict, Optional
from aliyunsdkcore import client
from aliyunsdkalidns.request.v20150109 import (
    DescribeDomainRecordsRequest,
    DeleteDomainRecordRequest,
    UpdateDomainRecordRequest,
    AddDomainRecordRequest
)

class AliDNS:
    LINE_MAP = {
        "默认": "default",
        "电信": "telecom",
        "联通": "unicom", 
        "移动": "mobile",
        "境外": "oversea",
        "default": "默认",
        "telecom": "电信", 
        "unicom": "联通",
        "mobile": "移动",
        "oversea": "境外"
    }

    def __init__(self, access_key_id: str, access_key_secret: str, region: str = 'cn-hongkong'):
        self.logger = logging.getLogger('AliDNS')
        self.client = client.AcsClient(access_key_id, access_key_secret, region)

    def get_record(self, domain: str, length: int, sub_domain: str, record_type: str) -> Dict:
        """获取域名解析记录"""
        try:
            request = DescribeDomainRecordsRequest.DescribeDomainRecordsRequest()
            request.set_accept_format('json')
            request.set_DomainName(domain)
            request.set_PageSize(length)
            request.set_RRKeyWord(sub_domain)
            request.set_Type(record_type)

            response = self.client.do_action_with_exception(request)
            return json.loads(response.decode())
        except Exception as e:
            self.logger.error(f"Failed to get records: {str(e)}")
            raise

    def create_record(self, domain: str, sub_domain: str, value: str, 
                     record_type: str = "A", line: str = "默认", ttl: int = 600) -> Dict:
        """创建域名解析记录"""
        try:
            request = AddDomainRecordRequest.AddDomainRecordRequest()
            request.set_accept_format('json')
            request.set_DomainName(domain)
            request.set_RR(sub_domain)
            request.set_Type(record_type)
            request.set_Value(value)
            request.set_Line(self.LINE_MAP.get(line, line))
            request.set_TTL(ttl)

            response = self.client.do_action_with_exception(request)
            return json.loads(response.decode())
        except Exception as e:
            self.logger.error(f"Failed to create record: {str(e)}")
            raise

    def update_record(self, domain: str, record_id: str, sub_domain: str, 
                     value: str, record_type: str = "A", line: str = "默认", ttl: int = 600) -> Dict:
        """更新域名解析记录"""
        try:
            request = UpdateDomainRecordRequest.UpdateDomainRecordRequest()
            request.set_accept_format('json')
            request.set_RecordId(record_id)
            request.set_RR(sub_domain)
            request.set_Type(record_type)
            request.set_Value(value)
            request.set_Line(self.LINE_MAP.get(line, line))
            request.set_TTL(ttl)

            response = self.client.do_action_with_exception(request)
            return json.loads(response.decode())
        except Exception as e:
            self.logger.error(f"Failed to update record: {str(e)}")
            raise

    def delete_record(self, domain: str, record_id: str) -> Dict:
        """删除域名解析记录"""
        try:
            request = DeleteDomainRecordRequest.DeleteDomainRecordRequest()
            request.set_accept_format('json')
            request.set_RecordId(record_id)

            response = self.client.do_action_with_exception(request)
            return json.loads(response.decode())
        except Exception as e:
            self.logger.error(f"Failed to delete record: {str(e)}")
            raise