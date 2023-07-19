# encoding:utf-8

import requests
import json
from bot.bot import Bot
from bridge.reply import Reply, ReplyType
from bot.session_manager import SessionManager
from bot.session_manager import Session
from common.log import logger
from config import conf, load_config


API_KEY = conf().get("baidu_wenxin_api_key")
SECRET_KEY = conf().get("baidu_wenxin_secret_key")

# Baidu Unit对话接口 (可用, 但能力较弱)
class ErnieTurboBot(Bot):

    def __init__(self):
        super().__init__()
        self.sessions = SessionManager(Session)
    def reply(self, query, context=None):
        session_id = context["session_id"]
        session = self.sessions.session_query(query, session_id)
        reply_content = self.reply_text(session)
        if reply_content["completion_tokens"] > 0:
            self.sessions.session_reply(reply_content["content"], session_id, reply_content["total_tokens"])

        reply = Reply(ReplyType.TEXT, reply_content["content"])
        return reply


    def reply_text(self, session) :

        try:
            url = "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/completions?access_token=" + self.get_access_token()
            payload = json.dumps({
                "messages": session.messages
            })
            headers = {
                'Content-Type': 'application/json'
            }
            response = requests.request("POST", url, headers=headers, data=payload)
            logger.info("[wenxin] response={}".format(response.text))

            return {
                "total_tokens": response.json()["usage"]["total_tokens"],
                "completion_tokens": response.json()["usage"]["completion_tokens"],
                "content": response.json()["result"],
            }
        except Exception:

            result = {"completion_tokens": 0, "content": "我要休息下，等会再来吧"}

            return result

    def get_access_token(self):
        """
        使用 AK，SK 生成鉴权签名（Access Token）
        :return: access_token，或是None(如果错误)
        """
        url = "https://aip.baidubce.com/oauth/2.0/token"
        params = {"grant_type": "client_credentials", "client_id": API_KEY, "client_secret": SECRET_KEY}
        return str(requests.post(url, params=params).json().get("access_token"))
