import imaplib
import email
from email.header import decode_header
import os
import telebot
import threading
import time
import sys
import html
import re

# читаем токен из файла
with open('DataFiles/token.txt', 'r') as f:
    token = f.read().strip()

# читаем данные для почты из файла
with open('DataFiles/maildata.txt', 'r') as f:
    lines = [line.strip() for line in f.readlines()]
    mail_server = lines[1]  # Адрес почтового сервера
    email_address = lines[3]  # Адрес вашей электронной почты
    password = lines[5]  # Пароль
    port = lines[7]  # Порт почтового сервера


# читаем список чатов из файла
with open('DataFiles/chats.txt', 'r') as f:
    lines = f.readlines()
    chat_ids = [line.strip() for line in lines[1:]]  # пропускаем первую строку (комментарий)

bot = telebot.TeleBot(token)

def check_mail():
    attempts = 0
    trys = 10
    while attempts < trys:
        try:
            # подключаемся к почтовому серверу
            mail = imaplib.IMAP4_SSL(mail_server, port=int(port))
            # логинимся
            mail.login(email_address, password)
            print("Подключение установлено")
            break
        except Exception as e:
            print(f"Не удалось подключиться к почтовому серверу: {e}")
            print("Повторная попытка через 1 минуту...")
            time.sleep(60)  # ждем 1 минуту перед повторной попыткой
            attempts += 1
    if attempts == trys:
        print("Не удалось подключиться к почтовому серверу после 10 попыток. Завершение работы.")
        bot.stop_polling()
        sys.exit(1)


    mail.select("inbox")

    # получаем непрочитанные письма
    result, data = mail.uid('search', None, "(UNSEEN)")
    email_ids = data[0].split()

    if email_ids:  # если есть непрочитанные сообщения
        latest_email_id = email_ids[-1]

        # получаем информацию о письме
        result, email_data = mail.uid('fetch', latest_email_id, '(BODY.PEEK[])')
        raw_email = email_data[0][1]
        email_message = email.message_from_bytes(raw_email)

        # помечаем сообщение как прочитанное
        mail.uid('store', latest_email_id, '+FLAGS', '(\Seen)')

        # получаем тему письма
        subject = decode_header(email_message['Subject'])[0][0]
        if isinstance(subject, bytes):
            subject = subject.decode()

        # получаем тело письма
        body = ""
        attachments = []
        if email_message.is_multipart():
            for part in email_message.get_payload():
                if part.get_content_type() == "text/plain":
                    body = part.get_payload(decode=True)
                elif part.get_content_type().startswith("image/"):
                    # это вложение-изображение, сохраняем его
                    image_data = part.get_payload(decode=True)
                    image_name = part.get_filename()
                    if image_name:
                        image_name = "".join(c for c in image_name if c.isalnum() or c in "._-")
                        with open(image_name, 'wb') as f:
                            f.write(image_data)
                        attachments.append(image_name)
        else:
            body = email_message.get_payload(decode=True)

        return subject, body, attachments
    else:  # если нет непрочитанных сообщений
        print("Нет непрочитанных сообщений.")
        # ждем 10 минут
        time.sleep(600)
        return None, None, None

def check_mail_periodically():
    while True:
        subject, body, attachments = check_mail()
        if subject is None and body is None:
            continue
        else:
            # Заменяем <br> на \n для переноса строки
            body = body.decode().replace('<br>', '\n')
            # Заменяем <b> и </b> на * для форматирования в стиле Markdown
            body = body.replace('<b>', '').replace('</b>', '')
            # Удаляем теги <span> и </span>
            body = body.replace('<span>', '').replace('</span>', '')
            # Заменяем HTML-сущности на обычный текст
            body = html.unescape(body)
            # Экранируем только символы [ и ], которые могут вызвать проблемы в MarkdownV2
            body = re.sub(r'(_*\[\~`>#\+\-=|{}.!])', r'\\\1', body)
            
            # отправляем сообщение в каждый чат из списка
            for chat_id in chat_ids:
                try:
                    bot.send_message(chat_id, f"Тема письма: {subject}\n\n{body}", parse_mode='Markdown')
                    for attachment in attachments:
                        with open(attachment, 'rb') as img:
                            bot.send_photo(chat_id, img)
                        os.remove(attachment)
                except telebot.apihelper.ApiException:
                    print(f"Не удалось отправить сообщение в чат {chat_id}. Возможно, бот не состоит в этом чате.")
        

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "Привет! Я бот, который проверяет новые письма на указанной почте и отправляет их в этот чат. Я автоматически проверяю почту каждые 10 минут.")

@bot.message_handler(commands=['addchat'])
def add_chat(message):
    # получаем ID чата из сообщения
    new_chat_id = message.text.split()[1]
    # проверяем, является ли введенный ID числом
    if not new_chat_id.isdigit():
        bot.reply_to(message, f"Введенный ID чата '{new_chat_id}' не является числом. Пожалуйста, введите корректный ID чата.")
        return
    # проверяем, есть ли уже такой ID в списке
    if new_chat_id in chat_ids:
        bot.reply_to(message, f"Чат {new_chat_id} уже добавлен.")
        return
    # добавляем его в список
    chat_ids.append(new_chat_id)
    # и записываем в файл
    with open('DataFiles/chats.txt', 'a') as f:
        f.write(f'\n{new_chat_id}')
    bot.reply_to(message, f"Чат {new_chat_id} был успешно добавлен.")

@bot.message_handler(content_types=['new_chat_members'])
def handle_new_chat_members(message):
    new_members = message.new_chat_members
    for member in new_members:
        if member.id == bot.get_me().id:
            # бот был добавлен в чат, добавляем ID чата в список и записываем в файл
            chat_id = str(message.chat.id)
            if chat_id not in chat_ids:
                chat_ids.append(chat_id)
                with open('DataFiles/chats.txt', 'a') as f:
                    f.write(f'\n{chat_id}')
                bot.send_message(chat_id, "Я был успешно добавлен в этот чат!")

@bot.message_handler(content_types=['left_chat_member'])
def handle_left_chat_member(message):
    left_member = message.left_chat_member
    if left_member.id == bot.get_me().id:
        # бот был удален из чата, удаляем ID чата из списка
        chat_id = str(message.chat.id)
        if chat_id in chat_ids:
            chat_ids.remove(chat_id)
            # и удаляем из файла
            with open('DataFiles/chats.txt', 'r') as f:
                lines = f.readlines()
            with open('DataFiles/chats.txt', 'w') as f:
                for line in lines:
                    if line.strip("\n") != chat_id:
                        f.write(line)

# создаем и запускаем новый поток, который будет проверять почту каждые 10 минут
threading.Thread(target=check_mail_periodically).start()

while True:
    try:
        bot.polling(none_stop=True, interval=10)
    except Exception as e:
        print(f"Ошибка: {e}. Повторная попытка через 5 секунд.")
        time.sleep(5)