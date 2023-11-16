import json
import re
from datetime import datetime

import openai
import requests
import unicodedata

import plugins
import os

from bridge.context import ContextType
from bridge.reply import Reply, ReplyType
from plugins import *
from common.log import logger
from plugins.gpt_fc import function as fun
from bot.openai.open_ai_vision import describe_image
from db.redis_util import RedisUtil
from common import redis_key_const
from common import const
from bot.bot_factory import create_bot


@plugins.register(name="NewGpt", desc="GPT函数调用，实现联网", desire_priority=99, version="0.1", author="chazzjimel", )
class NewGpt(Plugin):
    def __init__(self):
        super().__init__()
        self.count_max_tokens = None
        self.max_tokens = None
        self.temperature = None
        self.functions_openai_model = None
        self.assistant_openai_model = None
        self.app_sign = None
        self.app_key = None
        self.bing_subscription_key = None
        self.alapi_key = None
        self.prompt = None
        self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
        curdir = os.path.dirname(__file__)
        config_path = os.path.join(curdir, "config.json")
        logger.info(f"[NewGpt] current directory: {curdir}")
        logger.info(f"加载配置文件: {config_path}")
        logger.info("[NewGpt] inited")
        if not os.path.exists(config_path):
            logger.info('[RP] 配置文件不存在，将使用config.json.template模板')
            config_path = os.path.join(curdir, "config.json.template")
            logger.info(f"[NewGpt] config template path: {config_path}")

    def on_handle_context(self, e_context: EventContext):
        if e_context["context"].type not in [
            ContextType.TEXT
        ]:
            return
        context = e_context["context"]
        content = e_context["context"].content
        user_id = context["msg"].actual_user_id if context.get("isgroup", False) else context[
            "msg"].from_user_id
        pattern_cv = r"取消语音|取消音频|取消语音回复|取消音频回复|不要生成音频"
        pattern_sv = r"语音回复| 语音回复我$|回复语音|用语音| 生成音频$|生成音频给我$|生成语音$|生成语音给我$"
        pattern_sl = r"^用日语|^用韩语|^用英语|^用德语|^用粤语|^用葡萄牙语|^用印度语|^用越南语|^用朝鲜语|^用马来西亚语|^用俄语"
        if re.search(pattern_cv, content):
            e_context["context"]["desire_rtype"] = ReplyType.TEXT
            redis_key = redis_key_const.VOICE_REPLY_PRE + user_id
            RedisUtil().delete_key(redis_key)
        elif re.search(pattern_sl, content):
            e_context["context"]["desire_rtype"] = ReplyType.VOICE
            return
        elif re.search(pattern_sv, content):
            # 替换所有匹配的子串为空字符串
            filter_context = re.sub(pattern_sv, "", content).strip()
            if len(filter_context) == 0:
                redis_key = redis_key_const.VOICE_REPLY_PRE + user_id
                RedisUtil().set_key_with_expiry(redis_key, "1", 3600)
                reply = Reply()  # 创建一个回复对象
                reply.type = ReplyType.TEXT
                reply.content = "好的,接下来我将用语音回复你。"
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return
            e_context["context"].content = filter_context
            e_context["context"]["desire_rtype"] = ReplyType.VOICE
        else:
            redis_key = redis_key_const.VOICE_REPLY_PRE + user_id
            redis_value = RedisUtil().get_key(redis_key)
            if redis_value and int(redis_value) == 1:
                e_context["context"]["desire_rtype"] = ReplyType.VOICE

        if not conf().get("gpt_enable", True):
            return

        curdir = os.path.dirname(__file__)
        config_path = os.path.join(curdir, "config.json")
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                logger.debug(f"[NewGpt] config content: {config}")
                self.alapi_key = config["alapi_key"]
                self.bing_subscription_key = config["bing_subscription_key"]
                self.functions_openai_model = config['functions_openai_model']
                self.assistant_openai_model = config["assistant_openai_model"]
                self.app_key = config["app_key"]
                self.app_sign = config["app_sign"]
                self.temperature = config.get("temperature", 0.9)
                self.max_tokens = config.get("max_tokens", 1000)
        except Exception as e:
            if isinstance(e, FileNotFoundError):
                logger.warn(f"[RP] init failed, config.json not found.")
            else:
                logger.warn("[RP] init failed." + str(e))
            raise e
        reply = Reply()  # 创建一个回复对象
        if "help" in content or "帮助" in content:  # 如果用户请求帮助
            reply.type = ReplyType.INFO
            reply.content = self.get_help_text(verbose=True)
        else:
            context = e_context['context'].content[:]
            conversation_output = self.run_conversation(context, e_context)
            if conversation_output is not None:
                reply = Reply()  # 创建一个回复对象
                reply.type = ReplyType.TEXT
                reply.content = conversation_output
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
            else:
                return

    def run_conversation(self, context, e_context: EventContext):
        global function_response
        messages = []
        content = context
        logger.debug(f"User input: {content}")  # 用户输入

        messages.append({
            "role": "user",
            "content": content
        })
        openai.api_base = conf().get("open_ai_api_base")
        openai.api_key = conf().get("open_ai_api_key")
        openai.proxy = conf().get("proxy")
        response = openai.ChatCompletion.create(
            model=self.functions_openai_model,
            messages=messages,
            max_tokens=100,
            functions=[
                {
                    "name": "get_weather",
                    "description": "获取全球指定城市的天气信息,获取当前日期和时间",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "cityNm": {
                                "type": "string",
                                "description": "City names using Chinese characters, such as: 武汉, 广州, 深圳, 东京, 伦敦",
                            },

                        },
                        "required": ["cityNm"],
                    },
                },
                {
                    "name": "get_date",
                    "description": "获取日期相关信息,比如今天是几号,明天是几号,昨天是几号,今天星期几等",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                    },
                },
                {
                    "name": "search_bing",
                    "description": "搜索工具,根据用户输入的内容获取最新和实时信息,关键字：搜, 最新, 新闻",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "查询内容",
                            }
                        },
                        "required": ["query"],
                    },
                },

                {
                    "name": "ask_image",
                    "description": "解读和理解图片内容, 比如：图片里有什么？图片中问题怎么答？",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                },
            ],
            function_call="auto",
        )

        message = response["choices"][0]["message"]

        # 检查模型是否希望调用函数
        if message.get("function_call"):
            function_name = message["function_call"]["name"]
            logger.debug(f"Function call: {function_name}")  # 打印函数调用
            logger.debug(f"message={message}")

            if function_name == "search_bing":
                function_args_str = message["function_call"].get("arguments", "{}")
                function_args = json.loads(function_args_str)  # 使用 json.loads 将字符串转换为字典
                search_query = function_args.get("query", "未指定关键词")

                if e_context["context"].get("desire_rtype") == ReplyType.VOICE:
                    filtered_urls = fun.search_bing_url(subscription_key=self.bing_subscription_key, query=search_query,
                                                        count=5)
                    pattern = r"https://www\.msn\.cn"
                    for url in filtered_urls:
                        unsupported = re.search(pattern, url)
                        if not unsupported:
                            return self.sum_url(url)
                else:
                    function_response = fun.search_bing(subscription_key=self.bing_subscription_key, query=search_query,
                                                        count=5)
                    logger.debug(f"Function response: {function_response}")
                    return function_response

            elif function_name == "get_weather" or function_name == "get_date":
                reply = create_bot(const.XUNFEI).reply(content, e_context["context"])
                return reply.content

            elif function_name == "ask_image":
                context = e_context["context"]
                user_id = context["msg"].actual_user_id if context.get("isgroup", False) else context[
                    "msg"].from_user_id

                # 检查token用量
                redis_client = RedisUtil()
                token_left_key = redis_key_const.TOKEN_LEFT_PRE + user_id;
                token_left = redis_client.get_key(token_left_key)
                if not token_left:
                    now = datetime.now()
                    end_of_day = datetime(now.year, now.month, now.day, 23, 59, 59)
                    remaining_seconds = (end_of_day - now).seconds
                    redis_client.set_key_with_expiry(token_left_key, conf().get("gpt4_token_per_day", 10000),
                                                     remaining_seconds - 1)
                elif int(token_left) <= 0:
                    return conf().get("gpt4_token_not_enough", "今日Token已用完")

                redis_key = redis_key_const.ASK_IMG_PRE + user_id
                logger.debug(f"redis_key : {redis_key}")
                file_path = redis_client.get_key(redis_key)
                # 如果不是个人图片 读取群图片
                if not file_path and context.get("isgroup", False):
                    group_key = redis_key_const.LATS_GROUP_IMG_PRE + context["msg"].from_user_id
                    file_path = redis_client.get_key(group_key)

                if file_path:
                    open_ai_response = describe_image(file_path.decode(), content)
                    function_response = open_ai_response.get('choices', [{}])[0].get('message', {}).get('content',
                                                                                                        'N/A')
                    total_tokens = open_ai_response.get('usage', {}).get('total_tokens')
                    redis_client.decrement(redis_key_const.TOKEN_LEFT_PRE + user_id, total_tokens)
                return function_response

        else:
            # 如果模型不希望调用函数，直接继续
            logger.debug(f"Model response: {message['content']}")  # 打印模型的响应
            return None

    def get_help_text(self, verbose=False, **kwargs):
        # 初始化帮助文本，说明利用 midjourney api 来画图
        help_text = "联网搜索最新信息"
        # 返回帮助文本
        return help_text

    def sum_url(self, content):
        meta = None
        headers = {
            'Content-Type': 'application/json',
            'WebPilot-Friend-UID': 'fatwang2'
        }
        logger.info("sum link: " + content)
        payload = json.dumps({"link": content})
        try:
            api_url = "https://gpts.webpilot.ai/api/visit-web"
            response = requests.request("POST", api_url, headers=headers, data=payload)
            response.raise_for_status()
            data = json.loads(response.text)
            meta = data.get('content')  # 获取data字段

        except requests.exceptions.RequestException as e:
            logger.info(e)
            # 如果meta获取成功，发送请求到OpenAI
        if meta and "error" not in meta:
            return self.opt_context(meta)

        return "哎呀,搜索数据失败啦,请换一个内容或者再问我一次。"

    def handle_search(self, content, e_context):
        meta = None
        headers = {
            'Content-Type': 'application/json',
            'WebPilot-Friend-UID': 'fatwang2'
        }
        payload = json.dumps({"ur": content})
        try:
            api_url = "https://gpts.webpilot.ai/api/visit-web"
            response = requests.request("POST", api_url, headers=headers, data=payload)
            response.raise_for_status()
            data = json.loads(response.text)
            meta = data.get('content')  # 获取data字段

        except requests.exceptions.RequestException as e:
            logger.error(f"An error occurred: {e}")

        if meta and "error" not in meta:
            return self.opt_context(meta)

        return "哎呀,搜索数据失败啦,请换一个内容或者再问我一次。"

    def opt_context(self, meta):
        try:
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {conf().get("open_ai_api_key")}'  # 使用你的OpenAI API密钥
            }
            data = {
                "model": "gpt-3.5-turbo-16k-0613",
                "messages": [
                    {"role": "system",
                     "content": "你是一个新闻专家，我会给你发一些网页内容，请你用简单明了的语言做总结,不超过500字"},
                    {"role": "user", "content": meta}
                ]
            }
            proxy = conf().get("proxy")
            proxies = {
                'http': proxy,
                'https': proxy,
            } if proxy else {}
            response = requests.post(
                conf().get("open_ai_api_base", "https://api.openai.com/v1") + "/chat/completions", headers=headers,
                data=json.dumps(data), proxies=proxies)
            response.raise_for_status()

            # 处理响应数据
            response_data = response.json()
            # 这里可以根据你的需要处理响应数据
            # 解析 JSON 并获取 content
            if "choices" in response_data and len(response_data["choices"]) > 0:
                first_choice = response_data["choices"][0]
                if "message" in first_choice and "content" in first_choice["message"]:
                    return first_choice["message"]["content"]
        except requests.exceptions.RequestException as e:
            # 处理可能出现的错误
            logger.error(f"Error calling OpenAI API: {e}")

    def contains_chinese(slef, s):
        for c in s:
            if 'CJK UNIFIED' in unicodedata.name(c):
                return True
        return False
