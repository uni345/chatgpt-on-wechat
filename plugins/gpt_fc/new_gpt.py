import json

import openai
import plugins
import os

from bridge.context import ContextType
from bridge.reply import Reply, ReplyType
from channel.chat_message import ChatMessage
from plugins import *
from common.log import logger
from plugins.gpt_fc import function as fun
from bot.openai.open_ai_vision import describe_image
from db.redis_util import RedisUtil


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
        ] or e_context["context"].kwargs.get("origin_ctype") == ContextType.VOICE:
            return

        curdir = os.path.dirname(__file__)
        config_path = os.path.join(curdir, "config.json")
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                logger.debug(f"[NewGpt] config content: {config}")
                self.alapi_key = config["alapi_key"]
                self.bing_subscription_key = config["bing_subscription_key"]
                self.functions_openai_model = conf().get("model","gpt-3.5-turbo")
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
        content = e_context['context'].content[:]  # 获取内容
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

        response = openai.ChatCompletion.create(
            model=self.functions_openai_model,
            messages=messages,
            functions=[

                {
                    "name": "search_bing",
                    "description": "搜索工具,比如查询天气、搜索最新新闻、头条资讯、当前日期时间等",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "关键词信息",
                            },
                            "count": {
                                "type": "string",
                                "description": "搜索页数,如无指定几页，默认10",
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
                search_count = function_args.get("count", 10)
                function_response = fun.search_bing(subscription_key=self.bing_subscription_key, query=search_query,
                                                    count=search_count)
                logger.debug(f"Function response: {function_response}")
                return function_response
            elif function_name == "ask_image":

                context = e_context["context"]
                redis_client = RedisUtil()
                if context.get("isgroup", False):
                    redis_key = context["msg"].from_user_id
                else:
                    redis_key = context["msg"].from_user_id
                logger.debug(f"redis_key : {redis_key}")
                file_path = redis_client.get_key(redis_key)
                function_response = None
                if file_path:
                    function_response = describe_image(file_path, content)

                return function_response

        else:
            # 如果模型不希望调用函数，直接打印其响应
            logger.debug(f"Model response: {message['content']}")  # 打印模型的响应
            return message['content']

    def get_help_text(self, verbose=False, **kwargs):
        # 初始化帮助文本，说明利用 midjourney api 来画图
        help_text = "GPT函数调用，实现联网\n"
        # 返回帮助文本
        return help_text
