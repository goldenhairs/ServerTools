# -*- coding:utf-8 -*-
import re
import sys
import time
import queue
import peewee
import datetime
import requests
import threading
sys.path.append('../')
sys.path.append('../../')

from bs4 import BeautifulSoup
from playhouse.shortcuts import model_to_dict

from Common.Tools import Tools
from Common.wechat_sender import Wechat_Sender
from Common.Global_Var import Global_Var
from Common.model import AppPrice, App

count = 0
q = queue.Queue()


def get_app_price(app_name_id):
    '''
        爬取数据：接收app的Url后缀，返回app的名字和价格。
    '''
    global count
    count += 1

    response = requests.get("https://itunes.apple.com/cn/app/" + app_name_id)
    soup = BeautifulSoup(response.text, 'lxml')

    app_name = soup.find(class_='product-header__title app-header__title')

    app_price = soup.find(class_='inline-list__item inline-list__item--bulleted')
    if app_price == None or app_price == '' or app_price == 'None':
        app_price = soup.find(class_='inline-list__item inline-list__item--bulleted app-header__list__item--price')

    if app_name == None or app_price == None or app_price == '' or app_price == 'None':

        globalvar = Global_Var()
        app_price_monitor_mail_flag = globalvar.get_value('app_price_monitor_mail_flag')

        if count >= 10 and app_price_monitor_mail_flag == 1:
            content = 'app name is ' + str(app_name) + 'app price is ' + str(app_price) + '\n' + response.text
            ms = MailSender('AppPriceMonitorError', 'Crawling data failed!!!', content)
            ms.send_it()

            globalvar.set_value('app_price_monitor_mail_flag', 0)
            threading.Timer(21600, count_time_thread).start()

            return (None, None)
        else:
            get_app_price(app_name_id)

    for name in app_name.strings:
        app_name = name.strip()
        break

    if app_price.text == '免费':
        app_price = 0.0
    else:
        app_price = float(app_price.text.split('¥')[1])

    return (app_name, app_price)


def app_price_monitor(app_dict):
    '''
        价格监控：接收格式化的app dict，如果超过阈值则触发邮件通知。
    '''
    content = ''
    globalvar = Global_Var()

    for key in app_dict.keys():
        app_name, app_price = get_app_price(key)
        save_data(app_name, app_price)

        if app_price <= float(app_dict[key]):
            content = content + '\n' + '[' + app_name + ']' + ' is ¥' + str(app_price) + ' now !' + '\n'

    if content != '':
        app_price_monitor_mail_flag = globalvar.get_value('app_price_monitor_mail_flag')

        if app_price_monitor_mail_flag == "None":
            globalvar.set_value('app_price_monitor_mail_flag', 1)
            app_price_monitor_mail_flag = globalvar.get_value('app_price_monitor_mail_flag')

        if app_price_monitor_mail_flag == 1:
            ws = Wechat_Sender()
            ws.send('App Discount!', content)
            globalvar.set_value('app_price_monitor_mail_flag', 0)
            threading.Timer(21600, count_time_thread).start()


def count_time_thread():
    '''
        防止推送邮件被多次触发设置的flag。
        flag为1时可以发送，为0时不能发送
    '''
    globalvar = Global_Var()
    globalvar.set_value('app_price_monitor_mail_flag', 1)


def print_result_order_by_length(app_dict):
    '''
        按照app标题长度由短到长打印结果至控制台，无邮件通知逻辑。
        接收格式化的app dict，打印相关信息于控制台。
    '''
    print(time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time())) + ' Working...')

    result = []
    count = 0

    for key in app_dict.keys():
        Tools().show_process_bar(count, int(len(app_dict)))
        app_name, app_price = get_app_price(key)
        result.append([app_name, app_price])
        count += 1

    for x in range(len(result)):
        for y in range(len(result) - x - 1):
            chinese_length_1 = len(re.findall(r'[\u4e00-\u9fff]', result[y][0]))
            chinese_length_2 = len(re.findall(r'[\u4e00-\u9fff]', result[y + 1][0]))

            if 2 * chinese_length_1 + 1 * (len(result[y][0]) - chinese_length_1) > 2 * chinese_length_2 + 1 * (len(result[y + 1][0]) - chinese_length_2):
                result[y][0], result[y + 1][0] = result[y + 1][0], result[y][0]
                result[y][1], result[y + 1][1] = result[y + 1][1], result[y][1]

    print('=' * 20 + time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time())) + '=' * 20)

    for x in range(len(result)):
        print(str(result[x][0]) + ' : ' + '¥' + str(result[x][1]))

    print('=' * 59)


def get_app_price_and_count(app_name_id):
    '''
        适用于多线程的价格监控逻辑
    '''
    print('working...')
    app_name, app_price = get_app_price(app_name_id)
    q.put({app_name: app_price})


def mutiple_thread(app_dict):
    '''
        多线程爬取数据
    '''
    result = {}
    len_app_dict = len(app_dict)
    start_times = int(len(app_dict) / 5)
    print(start_times)
    start_times_left = len(app_dict) % 5
    print(start_times_left)
    for x in range(start_times):
        for i in range(5):
            app_name_id = app_dict.popitem()[0]
            thread_t = threading.Thread(target=get_app_price_and_count, args=(app_name_id, ))
            thread_t.setDaemon(True)
            thread_t.start
            #Tools().show_process_bar(5 * x + i, len_app_dict)
        for t in range(100):
            if q.qsize() == 5:
                while not q.empty():
                    temp_result = q.get()
                    print(temp_result)
                    result = dict(result, **q.get())
                break
            else:
                time.sleep(0.5)
    for x in range(start_times_left):
        app_name_id = app_dict.popitem()[0]
        thread_t = threading.Thread(target=get_app_price_and_count, args=(app_name_id, ))
        thread_t.setDaemon(True)
        thread_t.start
        #Tools().show_process_bar(5 * start_times + x, len_app_dict)
        for t in range(100):
            if q.qsize() == start_times_left:
                while not q.empty():
                    temp_result = q.get()
                    print(temp_result)
                    result = dict(result, **q.get())
                break
            else:
                time.sleep(0.5)
    print(result)


def save_data(app_name, app_price):
    try:
        crawling_times = int(len(AppPrice.select().where((AppPrice.date == datetime.datetime.now().date()) & (AppPrice.app_name == app_name))))
    except Exception:
        crawling_times = 0
    p = AppPrice(app_name=app_name, price=app_price, date=datetime.datetime.now().date(), crawling_times=crawling_times, time=datetime.datetime.now().strftime('%H:%M:%S'))
    p.save()
    return ('app price saved...')


app_dict = {}
for query in App.select().where(App.is_valid==1):
    dict_temp = model_to_dict(query)
    app_dict[dict_temp['app_name']] = int(dict_temp['expect_price'])
print_result_order_by_length(app_dict)
app_price_monitor(app_dict)
'''
app_dict = {
    'webssh-pro/id497714887': 0,
    'p.m.-splayer-free/id1009747025': 0,
    '7-billion-humans/id1393923918': 0,
    'pico-图像标注/id1395700699': 0,
    'app/id1207354572': 0,
    'app/id1372681079': 0,
    '我的足迹/id1299001064': 0,
    'gorogoa/id1269225754': 0,
    'hyper-ping/id1276204653': 0,
    'cloud-speed/id1299527944': 0,
    'onescreen-带壳截屏自由创作/id1355476695': 0,
    'thor-http-抓包嗅探分析-接口调试-网络协议/id1210562295': 0
}
'''
'''
#mutiple_thread(app_dict)
thread_t=threading.Thread(target=get_app_price_and_count, args=('webssh-pro/id497714887', ))
thread_t.setDaemon(True)
thread_t.start
while not q.empty():
    temp_result = q.get()
    print(temp_result)
'''