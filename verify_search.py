from knowledge_base import KnowledgeBase
import os
import shutil

# Создаем временную директорию для теста
test_kb_dir = "/tmp/test_kb_demo"
if os.path.exists(test_kb_dir):
    shutil.rmtree(test_kb_dir)
os.makedirs(test_kb_dir)

# Создаем файл с тестовыми данными
with open(os.path.join(test_kb_dir, "test.md"), "w", encoding="utf-8") as f:
    f.write("# Бронирование тура\nДля бронирования свяжитесь с менеджером.\n\n# Политика возврата\nВозврат средств осуществляется в течение 14 дней.")

# Инициализируем KnowledgeBase
kb = KnowledgeBase(test_kb_dir)

# Тестируем поиск
print("--- Тест поиска 'бронирование' ---")
results = kb.search("бронирование")
for i, res in enumerate(results):
    print(f"Результат {i+1}:\n{res}\n")

# Тестируем поиск
print("--- Тест поиска 'возврат' ---")
results = kb.search("возврат")
for i, res in enumerate(results):
    print(f"Результат {i+1}:\n{res}\n")

# Очистка
shutil.rmtree(test_kb_dir)
