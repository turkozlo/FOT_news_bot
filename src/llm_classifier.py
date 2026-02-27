import json
from pathlib import Path
import re

print("[LLM MODULE] llm_classifier.py загружен")

# Загрузка промптов
PROMPTS_PATH = Path("config/prompts.json")
with open(PROMPTS_PATH, "r", encoding="utf-8-sig") as f:
    PROMPTS = json.load(f)

# Загрузка конфигурации LLM и бэкенда
with open("config/llm_config.json", "r", encoding="utf-8") as f:
    llm_conf = json.load(f)

llm_backend = llm_conf.get("llm_backend", 0)

if llm_backend == 0:
    print("Используется OpenAI")
    from openai import OpenAI
    client = OpenAI(
        base_url=llm_conf["base_url_Open_AI"],
        api_key=llm_conf["api_key_Open_AI"],
    )
elif llm_backend == 1:
    print("Используется LangChain+Groq")
    from langchain_groq import ChatGroq
    from langchain_core.messages import HumanMessage
    client = ChatGroq(
        model=llm_conf.get("model_LANGCHAIN", "llama3-8b-8192"),
        api_key=llm_conf["api_key_LANGCHAIN"]
    )
else:
    print("Используется LangChain+Mistral")
    from langchain_mistralai import ChatMistralAI
    from langchain_core.messages import HumanMessage

    client = ChatMistralAI(
        model_name=llm_conf.get("model_LANGCHAIN_mistral", "mistral-medium-latest"),
        api_key=llm_conf["api_key_LANGCHAIN_mistral"]
    )

DEPARTMENTS = [
    "Кибербезопасность",
    "Региональный Государственный Сектор",
    "Бизнес",
    "Юристы",
    "Комплаенс"
]

import asyncio

# Глобальный семафор для ограничения RPS (1 запрос в 1.2 секунды для Mistral Free)
llm_semaphore = asyncio.Semaphore(1)

def clean_department_response(resp: str) -> list[str]:
    resp = resp.strip()
    parts = [item.strip(" '\"*").lower() for item in resp.split(",") if item.strip()]
    departments_lower = [d.lower() for d in DEPARTMENTS]
    result = [DEPARTMENTS[i] for i, d in enumerate(departments_lower) if d in parts]
    return result or ["Без категории"]

def clean_rating_response(resp: str) -> int:
    match = re.search(r"(-?\d+)", resp)
    if not match:
        return 0
    try:
        val = int(match.group(1))
        return max(1, min(val, 10))
    except ValueError:
        return 0

async def classify_department(news_text: str) -> list[str]:
    prompt = PROMPTS["classification"].format(
        departments=", ".join(DEPARTMENTS),
        text=news_text
    )
    
    max_retries = 5
    current_delay = 2.0
    
    async with llm_semaphore:
        for attempt in range(max_retries + 1):
            try:
                if llm_backend == 0:
                    resp = client.chat.completions.create(
                        model=llm_conf["model_Open_AI"],
                        extra_body={},
                        messages=[{"role": "user", "content": prompt}]
                    )
                    raw = resp.choices[0].message.content
                else:
                    # Используем ainvoke для LangChain
                    res = await client.ainvoke([HumanMessage(content=prompt)])
                    raw = res.content

                print(f"Сырой ответ модели: {raw}")
                # Обязательная пауза ПОСЛЕ успешного запроса, чтобы не частить (1.2с для запаса)
                await asyncio.sleep(1.2)
                
                depts = clean_department_response(raw)
                print(f"[DEBUG] Классифицировано в департаменты: {depts}")
                return depts
                
            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "rate" in error_str.lower():
                    if attempt < max_retries:
                        print(f"[CLASSIFY] Rate limit (429). Retrying in {current_delay}s... (Attempt {attempt + 1}/{max_retries})")
                        await asyncio.sleep(current_delay)
                        current_delay *= 2
                        continue
                print(f"[ERROR CLASSIFY] {e}")
                return ["Без категории"]
    
    return ["Без категории"]

async def rate_engagement(text: str, department: str) -> int:
    prompt = PROMPTS["rating"].format(
        department=department or "общей аудитории",
        text=text
    )
    
    max_retries = 5
    current_delay = 2.0
    
    async with llm_semaphore:
        for attempt in range(max_retries + 1):
            try:
                if llm_backend == 0:
                    resp = client.chat.completions.create(
                        model=llm_conf["model_Open_AI"],
                        extra_body={},
                        messages=[{"role": "user", "content": prompt}],
                    )
                    raw = resp.choices[0].message.content
                else:
                    res = await client.ainvoke([HumanMessage(content=prompt)])
                    raw = res.content

                await asyncio.sleep(1.2)
                rating = clean_rating_response(raw)
                print(f"[DEBUG] Интересность новости: {rating}")
                return rating
                
            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "rate" in error_str.lower():
                    if attempt < max_retries:
                        print(f"[RATING] Rate limit (429). Retrying in {current_delay}s... (Attempt {attempt + 1}/{max_retries})")
                        await asyncio.sleep(current_delay)
                        current_delay *= 2
                        continue
                print(f"[LLM RATING ERROR] {e}")
                return 0
    
    return 0


if __name__ == "__main__":
    # Тестовые новости
    test_news = ["Дмитрий Демешин поручил активизировать работу со спортивными федерациями в Хабаровском крае 📍Из 108 действующих региональных спортивных федераций 100 имеют аккредитацию на развитие вида спорта, 8 находятся в процессе получения аккредитации. Ключевой фактор развития спорта – проведение официальных соревнований. Министерство спорта края помогает в организации чемпионатов, первенств края и ДФО, всероссийских соревнований. ➡️Глава региона отметил низкую активность большинства спортивных федераций. 40 федераций существенно понизили число занимающихся их видом спорта, 33 из 100 аккредитованных имеют показатель «ноль». 48 федераций имеют нулевые показатели по количеству межрегиональных, всероссийских, международных соревнований, кубков. По словам Дмитрия Демешина, меры по отношению к таким организациям могут быть жёсткими – вплоть до лишения аккредитации. ✔️ Вице-губернатору Артему Мельникову и минспорта края поручено провести анализ работы спортивных федераций и организовать коллегию с их руководителями."]

    print("🔧 Тест классификации департамента:")
    depts = classify_department(test_news)
    print(f"Тест: {depts}  —  \"{test_news[:60]}…\"")