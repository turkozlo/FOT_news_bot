import json
import asyncio
from pathlib import Path

print("[LLM MODULE] offer_generator.py загружен")

# --- Загрузка конфигурации LLM ---
LLM_CONFIG_PATH = Path("newsendingbot/llm_config.json")
with open(LLM_CONFIG_PATH, "r", encoding="utf-8") as f:
    llm_conf = json.load(f)

llm_backend = llm_conf.get("llm_backend", 0)

# --- Инициализация клиента LLM ---
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

async def generate_offer_async(news_text: str, system_prompt: str) -> str | None:
    """
    Асинхронно генерирует текст оффера на основе новости через LLM.
    Возвращает строку (результат) или None при ошибке/недоступности LLM.
    """
    try:
        user_prompt = f"Вот текст новости:\n{news_text}"
        
        max_retries = 5
        current_delay = 2.0
        
        for attempt in range(max_retries + 1):
            try:
                if llm_backend == 0:
                    # OpenAI (синхронный клиент, запускаем в треде чтобы не блокировать loop)
                    def _call_openai():
                        response = client.chat.completions.create(
                            model=llm_conf["model_Open_AI"],
                            extra_body={},
                            max_tokens=512,
                            messages=[
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_prompt}
                            ],
                        )
                        return response.choices[0].message.content.strip()

                    result = await asyncio.to_thread(_call_openai)
                    print(f"[OFFER_GENERATOR][OpenAI] Сгенерирован оффер: {result}")
                    return result

                # --- LangChain (Groq / Mistral) ---
                # Попытка импортировать SystemMessage и HumanMessage из разных модулей
                SystemMessage = None
                HumanMessage = None
                try:
                    from langchain_core.messages import HumanMessage, SystemMessage
                except Exception:
                    try:
                        from langchain_core.schema import HumanMessage, SystemMessage
                    except Exception:
                        try:
                            from langchain_core.messages import HumanMessage
                        except Exception:
                            HumanMessage = None

                # Сформируем список сообщений для invoke
                messages = []
                if SystemMessage is not None and HumanMessage is not None:
                    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
                elif HumanMessage is not None:
                    messages = [HumanMessage(content=f"{system_prompt}\n\n{user_prompt}")]
                else:
                    messages = [f"SYSTEM: {system_prompt}\n\nUSER: {user_prompt}"]

                # Вызов клиента LangChain: используем ainvoke (асинхронно)
                resp = await client.ainvoke(messages)
                
                # Обработка ответа
                if hasattr(resp, "content"):
                    result = resp.content.strip()
                elif isinstance(resp, (list, tuple)) and len(resp) > 0:
                    first = resp[0]
                    result = getattr(first, "content", str(first)).strip()
                else:
                    result = str(resp).strip()

                print(f"[OFFER_GENERATOR][LangChain] Сгенерирован оффер: {result}")
                return result
            
            except Exception as e:
                # Проверяем на ошибку 429 (Rate Limit)
                error_str = str(e)
                if "429" in error_str or "Too Many Requests" in error_str:
                    if attempt < max_retries:
                        print(f"[OFFER_GENERATOR] Rate limit hit (429). Retrying in {current_delay}s... (Attempt {attempt + 1}/{max_retries})")
                        await asyncio.sleep(current_delay)
                        current_delay *= 2
                        continue
                
                raise e

    except Exception as e:
        print(f"[OFFER_GENERATOR ERROR] {e}", flush=True)
        return None
