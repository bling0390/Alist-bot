# -*- coding: UTF-8 -*-

import datetime
import json
import logging
import os

import requests
import telegram
import yaml
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import Update, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, filters, MessageHandler

from config.config import config, admin, bot_token, alist_host, alist_token, backup_time, write_config

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# bot菜单
bot_menu = [BotCommand(command="start", description="开始"),
            BotCommand(command="s", description="搜索文件"),
            BotCommand(command="sl", description="设置搜索结果数量"),
            BotCommand(command="zl", description="开启/关闭 直链"),
            BotCommand(command="st", description="存储管理"),
            BotCommand(command="cf", description="查看当前配置"),
            BotCommand(command="bc", description="备份Alist配置"),
            BotCommand(command="sbt", description="设置定时备份"),
            ]
scheduler = AsyncIOScheduler()


# 管理员验证
def admin_yz(func):  # sourcery skip: remove-unnecessary-else
    async def wrapper(update, context, *args, **kwargs):
        user_id = update.effective_user.id
        try:
            query = update.callback_query
            query_user_id = query.from_user.id
        except AttributeError:
            query_user_id = 2023

        if user_id in admin():
            return await func(update, context, *args, **kwargs)
        else:
            if query_user_id in admin():
                return await func(update, context, *args, **kwargs)
            else:
                await context.bot.send_message(chat_id=update.effective_chat.id, text="该命令仅管理员可用")

    return wrapper


# 开始
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="发送 /s+文件名 进行搜索")


# 设置菜单
@admin_yz
async def menu(update, context):
    await telegram.Bot(token=bot_token).set_my_commands(bot_menu)  # 全部可见
    await context.bot.send_message(chat_id=update.effective_chat.id,
                                   text="菜单设置成功，请退出聊天界面重新进入来刷新菜单")


# 查看当前配置
@admin_yz
async def cf(update, context):
    with open("config/config.yaml", 'r', encoding='utf-8') as f:
        cf_config = yaml.safe_load(f)
    with open("config/cn_dict.json", 'r', encoding='utf-8') as ff:
        cn_dict = json.load(ff)
    b = translate_key(translate_key(cf_config, cn_dict["config_cn"]), cn_dict["common"])
    text = json.dumps(b, indent=4, ensure_ascii=False)
    await context.bot.send_message(chat_id=update.effective_chat.id,
                                   text=f'<code>{text}</code>',
                                   parse_mode=telegram.constants.ParseMode.HTML)


# 监听普通消息
async def echo_bot(update, context):
    if "bc" in context.chat_data and context.chat_data["bc"]:
        message = update.message
        if message.reply_to_message:
            bc_message_id = context.chat_data.get("bc_message_id")
            if message.reply_to_message.message_id == bc_message_id.message_id:
                note_message_text = message.text
                await context.bot.delete_message(chat_id=message.chat.id,
                                                 message_id=message.message_id)
                await context.bot.edit_message_caption(chat_id=bc_message_id.chat.id,
                                                       message_id=bc_message_id.message_id,
                                                       caption=f'#Alist配置备份\n{note_message_text}')
        else:
            context.chat_data["bc"] = False
            context.chat_data.pop("bc_message_id", None)


# 备份alist配置
def backup_config():
    bc_list = ['setting', 'user', 'storage', 'meta']
    bc_dic = {'settings': '', 'users': 'users', 'storages': '', 'metas': ''}
    for i in range(len(bc_list)):
        bc_url = f'{alist_host}/api/admin/{bc_list[i]}/list'
        bc_header = {"Authorization": alist_token, 'accept': 'application/json'}
        bc_post = requests.get(bc_url, headers=bc_header)
        data = json.loads(bc_post.text)
        bc_dic[f'{bc_list[i]}s'] = data['data'] if i == 0 else data['data']['content']
    data = json.dumps(bc_dic, indent=4, ensure_ascii=False)  # 格式化json
    now = datetime.datetime.now()
    current_time = now.strftime("%Y_%m_%d_%H_%M_%S")  # 获取当前时间
    bc_file_name = f'alist_bot_backup_{current_time}.json'
    with open(bc_file_name, 'w', encoding='utf-8') as b:
        b.write(data)
    return bc_file_name


# 发送备份文件
@admin_yz
async def send_backup_file(update, context):
    bc_file_name = backup_config()
    context.chat_data["bc_message_id"] = await context.bot.send_document(chat_id=update.effective_chat.id,
                                                                         document=bc_file_name,
                                                                         caption='#Alist配置备份')
    context.chat_data["bc"] = True
    os.remove(bc_file_name)


# 设置备份时间&开启定时备份
async def set_backup_time(update, context):
    time = update.message.text.strip("/sbt ")
    if len(time.split()) == 5:
        config['bot']['backup_time'] = time
        write_config('config/config.yaml', config)
        if not scheduler.get_jobs():
            scheduler.add_job(send_backup_file, trigger=CronTrigger.from_crontab(backup_time()), args=(update, context),
                              id='send_backup_messages_regularly_id')
            scheduler.start()
        else:
            scheduler.reschedule_job('send_backup_messages_regularly_id',
                                     trigger=CronTrigger.from_crontab(backup_time()),
                                     args=(update, context))
        await context.bot.send_message(chat_id=update.effective_chat.id,
                                       text=f'设置成功：{backup_time()}\n已开启定时备份')

    elif time == '0':
        config['bot']['backup_time'] = time
        write_config('config/config.yaml', config)
        if scheduler.get_jobs():
            scheduler.pause_job('send_backup_messages_regularly_id')
        await context.bot.send_message(chat_id=update.effective_chat.id, text='已关闭定时备份')
    elif not time:
        text = '''格式：/sbt + 5位cron表达式，0为关闭

例：
<code>/sbt 0</code> 关闭定时备份
<code>/sbt 0 8 * * *</code> 每天上午8点运行
<code>/sbt 30 20 */3 * *</code> 每3天晚上8点30运行

 5位cron表达式格式说明
  ——分钟（0 - 59）
 |  ——小时（0 - 23）
 | |  ——日（1 - 31）
 | | |  ——月（1 - 12）
 | | | |  ——星期（0 - 7，星期日=0或7）
 | | | | |
 * * * * *
'''
        await context.bot.send_message(chat_id=update.effective_chat.id, text=text,
                                       parse_mode=telegram.constants.ParseMode.HTML)
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text='格式错误')


#####################################################################################

#####################################################################################


# 列表/字典key翻译，输入：待翻译列表/字典，翻译字典 输出：翻译后的列表/字典
def translate_key(list_or_dict, translation_dict):  # sourcery skip: assign-if-exp
    if isinstance(list_or_dict, dict):
        def translate_zh(_key):
            translate_dict = translation_dict
            # 如果翻译字典里有当前的key，就返回对应的中文字符串
            if _key in translate_dict:
                return translate_dict[_key]
            # 如果翻译字典里没有当前的key，就返回原字符串
            else:
                return _key

        new_dict_or_list = {}  # 存放翻译后key的字典
        # 遍历原字典里所有的键值对
        for key, value in list_or_dict.items():
            # 如果当前的值还是字典，就递归调用自身
            if isinstance(value, dict):
                new_dict_or_list[translate_zh(key)] = translate_key(value, translation_dict)
            # 如果当前的值不是字典，就把当前的key翻译成中文，然后存到新的字典里
            else:
                new_dict_or_list[translate_zh(key)] = value
    else:
        new_dict_or_list = []
        for index, value in enumerate(list_or_dict):
            if value in translation_dict.keys():
                new_dict_or_list.append(translation_dict[value])
            else:
                new_dict_or_list.append(value)
    return new_dict_or_list


#####################################################################################
#####################################################################################
def main():
    from search import search_handlers
    from storage import storage_handlers, echo_storage

    application = ApplicationBuilder().token(bot_token).build()

    bot_handlers = [
        CommandHandler('start', start),
        CommandHandler('bc', send_backup_file),
        CommandHandler('cf', cf),
        CommandHandler('menu', menu),
        CommandHandler('sbt', set_backup_time)
    ]

    # bot
    application.add_handlers(bot_handlers)

    # 监听普通消息
    async def e(update, context):
        await echo_storage(update, context)
        await echo_bot(update, context)

    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), e))

    # search
    application.add_handlers(search_handlers)

    # storage
    application.add_handlers(storage_handlers)

    # 启动
    application.run_polling()


if __name__ == '__main__':
    main()
