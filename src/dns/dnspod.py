#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
from tencentcloud.common import credential
from tencentcloud.dnspod.v20210323 import dnspod_client, models

class DNSPod:
    def __init__(self, secret_id: str, secret_key: str):
        self.cred = credential.Credential(secret_id, secret_key)
        self.client = dnspod_client.DnspodClient(self.cred, "")

    def get_record(self, domain: str, length: int, sub_domain: str, record_type: str) -> dict:
        req = models.DescribeRecordListRequest()
        params = {
            "Domain": domain,
            "Subdomain": sub_domain,
            "RecordType": record_type,
            "Limit": length
        }
        req.from_json_string(json.dumps(params))
        resp = self.client.DescribeRecordList(req)
        return json.loads(resp.to_json_string())

    def create_record(self, domain: str, sub_domain: str, value: str, 
                     record_type: str = "A", line: str = "默认", ttl: int = 600) -> dict:
        req = models.CreateRecordRequest()
        params = {
            "Domain": domain,
            "SubDomain": sub_domain,
            "RecordType": record_type,
            "RecordLine": line,
            "Value": value,
            "TTL": ttl
        }
        req.from_json_string(json.dumps(params))
        resp = self.client.CreateRecord(req)
        return json.loads(resp.to_json_string())

    def update_record(self, domain: str, record_id: int, sub_domain: str, 
                     value: str, record_type: str = "A", line: str = "默认", ttl: int = 600) -> dict:
        req = models.ModifyRecordRequest()
        params = {
            "Domain": domain,
            "RecordId": record_id,
            "SubDomain": sub_domain,
            "RecordType": record_type,
            "RecordLine": line,
            "Value": value,
            "TTL": ttl
        }
        req.from_json_string(json.dumps(params))
        resp = self.client.ModifyRecord(req)
        return json.loads(resp.to_json_string())

    def delete_record(self, domain: str, record_id: int) -> dict:
        req = models.DeleteRecordRequest()
        params = {
            "Domain": domain,
            "RecordId": record_id
        }
        req.from_json_string(json.dumps(params))
        resp = self.client.DeleteRecord(req)
        return json.loads(resp.to_json_string())