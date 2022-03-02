import dataframe_image as dfi
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters, JobQueue
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import pandas as pd
from datetime import datetime, time
import logging
import pickle

updater = Updater(token='TOKEN', use_context=True)
dispatcher = updater.dispatcher

logging.basicConfig(filename='logfile.log',
                    format='[%(asctime)s] - %(name)s - %(levelname)-s - %(funcName)s:  %(message)s',
                    datefmt='%H:%M:%S', level=logging.INFO)


def logs(update):
    # user = update.effective_user
    # # username = user.username
    # uid = user.id
    # logging.info('{} - {}'.format(users[uid].state, users[uid].notification_time))
    logging.info('{} - {}'.format(2, 3))


intensity = {0: 'не было',
             1: 'слегка',
             2: 'средне',
             3: 'сильно',
             4: 'очень сильно'}


class UserInfo:
    def __init__(self, params=None):
        if params is None:
            params = {'state': 'idle', 'smps': list(), 'process': set(), 'nt_tm': 'none',
                      'data': pd.DataFrame({'date': []}).set_index('date')}
        self.state = params["state"]
        self.symptoms = params['smps']
        self.process = params['process']
        self.notification_time = params['nt_tm']
        self.data = params['data']

    def add_symptoms(self, symptoms):
        self.symptoms.extend(symptoms)
        self.data[symptoms] = None
        self.process = set(self.symptoms)
        self.state = 'idle'


with open('symptoms.pickle', 'rb') as f:
    users = pickle.load(f)


def start(update, context):
    user_id = update.effective_chat.id
    # users_state[user_id] = 'idle'
    # user_notification[user_id] = True
    if user_id not in users:
        users[user_id] = UserInfo()
        # users[user_id] = pd.DataFrame({'date': []}).set_index('date')
    help_msg = '''
/fill - формчуча
/add - добавить симптом
/change_time - время уведов
/cancel - отменить уведомления
/make_file - сводная табличка (временно не работает)
/clear - очистить все (!) данные
/show_last - вывести последние данные
'''
    context.bot.send_message(user_id, help_msg)
    logs(update)


def help_me(update, context):
    help_msg = '''
/fill - формчуча
/add - добавить симптом
/change_time - время уведов
/cancel - отменить уведомления
/make_file - сводная табличка (временно не работает)
/clear - очистить все (!) данные
/show_last - вывести последние данные'''
    context.bot.send_message(update.effective_chat.id, help_msg)


def notification(context):
    context.bot.send_message(context.job.context, 'время заполнить данные. /fill')


def cancel(update, context):
    for job in context.job_queue.jobs():
        job.schedule_removal()
    context.bot.send_message(update.effective_chat.id, 'теперь не будут приходить уведомления.')


def change_time(update, context):
    user_id = update.effective_chat.id
    users[user_id].state = 'set_time'
    context.bot.send_message(user_id, 'напишите, в какое время хотите получать напоминание. (например, 12:00)')


def add(update, context):
    user_id = update.effective_chat.id
    users[user_id].state = 'add'
    # users_state[user_id] = 'add'
    msg = '''отправьте сообщение с симтомами в следующем формате:
симптом 1
симптом 2
...'''
    context.bot.send_message(user_id, msg)


def clear(update, context):
    user_id = update.effective_chat.id
    users[user_id] = UserInfo()
    for job in context.job_queue.jobs():
        job.schedule_removal()
    context.bot.send_message(user_id, 'готово.')
    save_results()
    logs(update)


def answer_txt(update, context):
    answer = update.message.text
    user_id = update.effective_chat.id
    if users[user_id].state == 'add':
        users[user_id].add_symptoms([symptom.strip() for symptom in answer.split('\n')])
        msg = '''симптомы добавлены.'''
        save_results()
        context.bot.send_message(user_id, msg)
    elif users[user_id].state == 'set_time':
        hour, minute = answer.split(':')
        context.job_queue.run_daily(notification, context=update.message.chat_id, time=time(hour, minute))
        context.bot.send_message(user_id, 'время установлено.')
        users[user_id].state = 'idle'
        users[user_id].notification_time = answer
    else:
        context.bot.send_message(user_id, 'игнор.')
    logs(update)


def make_file(update, context):
    user_id = update.effective_chat.id
    df = users[user_id].data
    dfi.export(df.style.bar(), "mytable.png")
    context.bot.send_photo(user_id, photo=open("mytable.png", 'rb'), caption='воть')


def show_last(update, context):
    msg, uid = '', update.effective_chat.id
    data = users[uid].data.iloc[-1, :]
    for x, y in enumerate(data):
        msg += '{}: {}\n'.format(users[uid].data.columns[x], intensity[y])
    context.bot.send_message(uid, msg)
    logs(update)


def fill(update, context):
    user_id = update.effective_chat.id
    users[user_id].state = 'fill'
    ind = datetime.now().strftime("%d/%m/%Y %H:%M")
    update.message.reply_text('как сегодня дела',
                              reply_markup=make_keyboard(ind, users[user_id].process))


def make_keyboard(ind, elements=None, symptom=None):
    if symptom is None:
        keyboard = [
            [InlineKeyboardButton(elem, callback_data=', '.join(['main', elem, ind]))]
            for elem in elements]
        keyboard.append([InlineKeyboardButton('завершить', callback_data='end')])
    else:
        keyboard = [
            [InlineKeyboardButton(intensity[num], callback_data=', '.join([symptom, str(num), ind]))]
            for num in range(5)]
    reply_markup = InlineKeyboardMarkup(keyboard)
    return reply_markup


def button(update, context):
    uid = update.effective_chat.id
    query = update.callback_query
    data = query.data
    query.answer()
    if data == 'end':
        users[uid].process = set(users[uid].symptoms)
        query.edit_message_text(text='готово!')
        save_results()
    elif data.startswith('main'):
        trash, symptom, ind = data.split(', ')
        query.edit_message_text(text='насколько сильно')
        update.callback_query.message.edit_reply_markup(
            reply_markup=make_keyboard(ind, symptom=symptom))
    else:
        symptom, score, ind = data.split(', ')
        users[uid].data.loc[ind, symptom] = int(score)
        query.edit_message_text(text='какие симптомы ощущали')
        users[uid].process.discard(symptom)
        if len(users[uid].process) > 0:
            update.callback_query.message.edit_reply_markup(
                reply_markup=make_keyboard(ind, elements=users[uid].process))
        else:
            users[uid].process = set(users[uid].symptoms)
            query.edit_message_text(text='готово!')
            save_results()
    logs(update)


def save_results():
    with open('symptoms.pickle', 'wb') as file:
        pickle.dump(users, file)


dispatcher.add_handler(CommandHandler('help', help_me))
dispatcher.add_handler(CommandHandler('start', start))
dispatcher.add_handler(CommandHandler('fill', fill))
dispatcher.add_handler(CommandHandler('change_time', change_time))
dispatcher.add_handler(CommandHandler('cancel', cancel))
dispatcher.add_handler(CommandHandler('clear', clear))
dispatcher.add_handler(CommandHandler('add', add))
dispatcher.add_handler(CommandHandler('show_last', show_last))
dispatcher.add_handler(CommandHandler('make_file', make_file))
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, answer_txt))

dispatcher.add_handler(CallbackQueryHandler(button))

updater.start_polling()
