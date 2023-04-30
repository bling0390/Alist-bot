# -*- coding: UTF-8 -*-
import json
import math
import urllib.parse

from pyrogram import filters
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from api.alist_api import search, fs_get
from bot import admin_yz
from config.config import config, per_page, z_url, alist_web, write_config


@admin_yz
async def sl(client, message):
    text_caps = message.text
    sl_str = text_caps.strip("/sl @")
    if sl_str.isdigit():
        config['bot']['search']['per_page'] = int(sl_str)
        write_config("config/config.yaml", config)
        await client.send_message(
            chat_id=message.chat.id, text=f"已修改搜索结果数量为：{sl_str}"
        )
    else:
        await client.send_message(chat_id=message.chat.id, text="请输入正整数")


# 设置直链
@admin_yz
async def zl(client, message):
    text_caps = message.text
    zl_str = text_caps.strip("/zl @")
    if zl_str == "1":
        config['bot']['search']['z_url'] = True
        await client.send_message(chat_id=message.chat.id, text="已开启直链")
    elif zl_str == "0":
        config['bot']['search']['z_url'] = False
        await client.send_message(chat_id=message.chat.id, text="已关闭直链")
    else:
        await client.send_message(chat_id=message.chat.id, text="请在命令后加上1或0(1=开，0=关)")
    write_config("config/config.yaml", config)


search_results = []
pointer = 0  # 翻页
pages = 1  # button默认页数


# 搜索
async def s(client, message):  # sourcery skip: low-code-quality
    text_caps = message.text
    s_str = text_caps.strip("/s @")
    search_results.clear()
    if s_str == "" or "_bot" in s_str:
        await client.send_message(chat_id=message.chat.id, text="请加上文件名，例：/s 巧克力")
    else:
        # 搜索文件
        alist_post = search(s_str)
        alist_post_json = json.loads(alist_post.text)
        if not alist_post_json['data']['content']:
            await client.send_message(chat_id=message.chat.id, text="未搜索到文件，换个关键词试试吧")
        else:
            search1 = await client.send_message(chat_id=message.chat.id, text="搜索中...")
            # 文件/文件夹名字 文件/文件夹路径 文件大小 是否是文件夹
            name_list = parent_list = size_list = is_dir_list = []
            count = 0
            tg_text = ""
            global pointer, pages
            pointer, pages, tt = 0, 1, 0
            for item in alist_post_json['data']['content']:
                name_list.append(item['name'])
                parent_list.append(item['parent'])
                size_list.append(item['size'])
                is_dir_list.append(item['is_dir'])
                file_name, path, file_size, folder = item['name'], item['parent'], item['size'], item['is_dir']

                file_url = alist_web + path + "/" + file_name

                # 获取文件直链
                if folder:
                    folder_tg_text = "📁文件夹："
                    z_folder_f = ''
                    z_url_link = ''
                elif z_url():
                    folder_tg_text = "📄文件："
                    z_folder = "直接下载"
                    z_folder_f = "|"
                    z_url_link = \
                        f'<a href="{json.loads(fs_get(f"{path}/{file_name}").text)["data"]["raw_url"]}">{z_folder}</a>'
                else:
                    folder_tg_text = "📄文件："
                    z_folder_f = ''
                    z_url_link = ''

                ########################
                file_url = urllib.parse.quote(file_url, safe=':/')
                text = f'''{count + 1}.{folder_tg_text}{file_name}
<a href="{file_url}">🌐打开网站</a>|{z_url_link}{z_folder_f}大小: {pybyte(file_size)}

'''
                #########################

                tg_text += text
                count += 1
                search_results.append(text)

                if count >= per_page() + 1:
                    continue
                tt = tg_text

            page_count = (len(search_results) + per_page() - 1) // per_page()
            search_button = [
                [
                    InlineKeyboardButton(f'1/{page_count}', callback_data='pages')
                ],
                [
                    InlineKeyboardButton('⬆️上一页', callback_data='previous_page'),
                    InlineKeyboardButton('⬇️下一页', callback_data='next_page')
                ],

            ]
            await client.edit_message_text(chat_id=message.chat.id,
                                           message_id=search1.id,
                                           text=tt,
                                           reply_markup=InlineKeyboardMarkup(search_button),
                                           disable_web_page_preview=True
                                           )


# 翻页
async def search_button_callback(client, message):
    query = message.data

    async def turn():
        text = search_results[pointer:pointer + 5]
        message_id = message.message.id
        tg_text = ''.join(text)
        search_button = [
            [
                InlineKeyboardButton(f'{pages}/{page_count}', callback_data='pages')
            ],
            [
                InlineKeyboardButton('⬆️上一页', callback_data='previous_page'),
                InlineKeyboardButton('⬇️下一页', callback_data='next_page')
            ],
        ]
        await client.edit_message_text(chat_id=message.message.chat.id,
                                       message_id=message_id,
                                       text=tg_text,
                                       reply_markup=InlineKeyboardMarkup(search_button),
                                       disable_web_page_preview=True
                                       )

    global pointer, pages
    if query != 'pages':
        page_count = (len(search_results) + per_page() - 1) // per_page()
        if query == 'next_page':
            if pages < page_count:
                pointer += 5  # 指针每次加5，表示下一页
                pages += 1
                await turn()
        elif query == 'previous_page':
            if pages > 1:
                pages -= 1
                pointer -= 5  # 指针每次加5，表示上一页
                await turn()


#####################################################################################

#####################################################################################

# 字节数转文件大小

def pybyte(size, dot=2):
    size = float(size)
    # 位 比特 bit
    if 0 <= size < 1:
        human_size = f'{str(round(size / 0.125, dot))}b'
    elif 1 <= size < 1024:
        human_size = f'{str(round(size, dot))}B'
    elif math.pow(1024, 1) <= size < math.pow(1024, 2):
        human_size = f'{str(round(size / math.pow(1024, 1), dot))}KB'
    elif math.pow(1024, 2) <= size < math.pow(1024, 3):
        human_size = f'{str(round(size / math.pow(1024, 2), dot))}MB'
    elif math.pow(1024, 3) <= size < math.pow(1024, 4):
        human_size = f'{str(round(size / math.pow(1024, 3), dot))}GB'
    elif math.pow(1024, 4) <= size < math.pow(1024, 5):
        human_size = f'{str(round(size / math.pow(1024, 4), dot))}TB'
    else:
        raise ValueError(
            f'{pybyte.__name__}() takes number than or equal to 0, but less than 0 given.'
        )
    return human_size


#####################################################################################
#####################################################################################

search_handlers = [
    MessageHandler(s, filters.command('s')),
    MessageHandler(sl, filters.command('sl')),
    MessageHandler(zl, filters.command('zl')),
    CallbackQueryHandler(search_button_callback),
]