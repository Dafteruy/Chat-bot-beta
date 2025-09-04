Если код выдаёт ошибку о .env

поменяйте код:

os.getenv('bot_token') => 'токен в кавычках'
os.getenv('admin_ids', '') => 'ID1', 'ID2' (в кавычках)

