import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../"))

from app.tasks.rag_tasks import answer_question_task

COMPANY_ID = "4d3ef371-7d0e-4111-91d0-aa8ffe7e0188"  # kendi company_id'n

# .delay() ile kuyruğa at (worker bunu arka planda işleyecek)
async_result = answer_question_task.delay(COMPANY_ID, "Yıllık izin hakkım ne zaman başlıyor?")

print(f"Görev kuyruğa atıldı, ID: {async_result.id}")
print("Sonuç bekleniyor...")

# .get() ile sonucu bekle (timeout: 60 saniye)
result = async_result.get(timeout=60)
print(f"Sonuç: {result}")
