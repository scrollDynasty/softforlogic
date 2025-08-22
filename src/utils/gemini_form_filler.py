import asyncio
import json
import base64
from typing import Dict, List, Optional, Any
from playwright.async_api import Page, ElementHandle
import google.generativeai as genai
from ..utils.logger import logger


class GeminiFormFiller:
    """AI-помощник для автоматического заполнения форм с помощью Google Gemini"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-2.5-flash')
        pass  # Логирование будет в load_parser.py
    
    async def fill_search_form(self, page: Page, search_criteria: Dict) -> bool:
        """
        Автоматически заполняет форму поиска грузов с помощью AI
        """
        try:
            logger.info("🧠 Начинаю AI-анализ формы поиска...")
            
            # Получаем скриншот страницы
            screenshot = await page.screenshot()
            screenshot_b64 = base64.b64encode(screenshot).decode()
            
            # Получаем HTML структуру формы
            form_html = await self._extract_form_elements(page)
            
            # Создаем промпт для AI
            prompt = self._create_form_filling_prompt(search_criteria, form_html)
            
            # Отправляем запрос в Gemini
            response = await self._get_gemini_response(prompt, screenshot_b64)
            
            # Парсим ответ AI
            actions = self._parse_ai_response(response)
            
            # Выполняем действия на странице
            success = await self._execute_form_actions(page, actions)
            
            if success:
                logger.info("✅ Форма успешно заполнена с помощью AI")
            else:
                logger.warning("⚠️ Не все поля формы удалось заполнить")
                
            return success
            
        except Exception as e:
            logger.error(f"❌ Ошибка AI-заполнения формы: {e}")
            return False
    
    async def _extract_form_elements(self, page: Page) -> str:
        """Извлекает структуру элементов формы"""
        try:
            # Находим все интерактивные элементы формы
            elements_info = await page.evaluate("""
                () => {
                    const elements = [];
                    
                    // Находим все селекты, инпуты, кнопки
                    const selectors = [
                        'select', 'input[type="text"]', 'input[type="email"]', 
                        'input[type="date"]', 'input[type="search"]', 'textarea',
                        'button[type="submit"]', 'button:contains("Search")',
                        'button:contains("Find")', 'input[type="submit"]'
                    ];
                    
                    selectors.forEach(selector => {
                        const els = document.querySelectorAll(selector);
                        els.forEach((el, index) => {
                            const rect = el.getBoundingClientRect();
                            if (rect.width > 0 && rect.height > 0) {  // Только видимые элементы
                                elements.push({
                                    type: el.tagName.toLowerCase(),
                                    inputType: el.type || '',
                                    name: el.name || '',
                                    id: el.id || '',
                                    className: el.className || '',
                                    placeholder: el.placeholder || '',
                                    value: el.value || '',
                                    text: el.textContent?.trim() || '',
                                    options: el.tagName === 'SELECT' ? 
                                        Array.from(el.options).map(opt => ({
                                            value: opt.value,
                                            text: opt.textContent.trim()
                                        })) : [],
                                    position: {
                                        x: Math.round(rect.left),
                                        y: Math.round(rect.top),
                                        width: Math.round(rect.width),
                                        height: Math.round(rect.height)
                                    },
                                    selector: el.id ? `#${el.id}` : 
                                             el.name ? `[name="${el.name}"]` :
                                             el.className ? `.${el.className.split(' ')[0]}` :
                                             `${el.tagName.toLowerCase()}:nth-of-type(${index + 1})`
                                });
                            }
                        });
                    });
                    
                    return elements;
                }
            """)
            
            return json.dumps(elements_info, indent=2)
            
        except Exception as e:
            logger.error(f"❌ Ошибка извлечения элементов формы: {e}")
            return "[]"
    
    def _create_form_filling_prompt(self, criteria: Dict, form_html: str) -> str:
        """Создает промпт для AI"""
        return f"""
Ты - эксперт по автоматизации веб-форм. Проанализируй форму поиска грузоперевозок и создай план заполнения.

ДАННЫЕ ДЛЯ ЗАПОЛНЕНИЯ:
{json.dumps(criteria, indent=2, ensure_ascii=False)}

СТРУКТУРА ФОРМЫ:
{form_html}

ЗАДАЧА:
1. Проанализируй все элементы формы
2. Сопоставь каждое поле из данных с соответствующим элементом формы
3. Создай план действий для заполнения формы

ОТВЕТ ДОЛЖЕН БЫТЬ В ФОРМАТЕ JSON:
{{
    "actions": [
        {{
            "action": "select_option",
            "selector": "#equipment-select",
            "value": "Dry Van",
            "field_purpose": "Тип оборудования"
        }},
        {{
            "action": "fill_input",
            "selector": "[name='origin']",
            "value": "GAFFNEY, SC",
            "field_purpose": "Место отправления"
        }},
        {{
            "action": "click_button",
            "selector": "button[type='submit']",
            "field_purpose": "Кнопка поиска"
        }}
    ]
}}

ВОЗМОЖНЫЕ ДЕЙСТВИЯ:
- select_option: выбор опции в селекте
- fill_input: заполнение текстового поля
- click_button: нажатие кнопки
- set_date: установка даты

ВАЖНО:
- Используй только селекторы из предоставленной структуры
- Сопоставляй поля по смыслу (например, origin_location -> поле "Origin" или "From")
- Учитывай типы данных (даты, числа, текст)
- Не создавай действия для несуществующих элементов
"""
    
    async def _get_gemini_response(self, prompt: str, screenshot_b64: str) -> str:
        """Отправляет запрос в Gemini AI"""
        try:
            # Создаем изображение из скриншота
            image_data = {
                'mime_type': 'image/png',
                'data': screenshot_b64
            }
            
            # Отправляем запрос с текстом и изображением
            response = self.model.generate_content([
                prompt,
                image_data
            ])
            
            return response.text
            
        except Exception as e:
            logger.error(f"❌ Ошибка запроса к Gemini: {e}")
            return ""
    
    def _parse_ai_response(self, response: str) -> List[Dict]:
        """Парсит ответ AI и извлекает действия"""
        try:
            # Ищем JSON в ответе
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            
            if json_start != -1 and json_end != -1:
                json_str = response[json_start:json_end]
                parsed = json.loads(json_str)
                return parsed.get('actions', [])
            
            logger.warning("⚠️ Не удалось найти JSON в ответе AI")
            return []
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ Ошибка парсинга JSON ответа: {e}")
            return []
    
    async def _execute_form_actions(self, page: Page, actions: List[Dict]) -> bool:
        """Выполняет действия на странице"""
        success_count = 0
        total_actions = len(actions)
        
        for action in actions:
            try:
                action_type = action.get('action')
                selector = action.get('selector')
                value = action.get('value')
                purpose = action.get('field_purpose', 'Неизвестное поле')
                
                logger.info(f"🎯 Выполняю: {purpose} ({action_type})")
                
                if action_type == 'select_option':
                    element = await page.wait_for_selector(selector, timeout=5000)
                    if element:
                        # Пробуем разные способы выбора опции
                        try:
                            await element.select_option(label=value)
                        except:
                            try:
                                await element.select_option(value=value)
                            except:
                                # Ищем опцию по частичному совпадению
                                options = await element.query_selector_all('option')
                                for option in options:
                                    text = await option.text_content()
                                    if value.lower() in text.lower() or text.lower() in value.lower():
                                        option_value = await option.get_attribute('value')
                                        await element.select_option(value=option_value)
                                        break
                        success_count += 1
                        logger.info(f"✅ Выбрано: {value}")
                
                elif action_type == 'fill_input':
                    element = await page.wait_for_selector(selector, timeout=5000)
                    if element:
                        await element.clear()
                        await element.fill(str(value))
                        success_count += 1
                        logger.info(f"✅ Заполнено: {value}")
                
                elif action_type == 'set_date':
                    element = await page.wait_for_selector(selector, timeout=5000)
                    if element:
                        # Конвертируем дату в нужный формат
                        date_value = self._format_date(value)
                        await element.fill(date_value)
                        success_count += 1
                        logger.info(f"✅ Дата установлена: {date_value}")
                
                elif action_type == 'click_button':
                    element = await page.wait_for_selector(selector, timeout=5000)
                    if element:
                        await element.click()
                        success_count += 1
                        logger.info(f"✅ Кнопка нажата")
                        # Ждем немного после нажатия кнопки поиска
                        await page.wait_for_timeout(1000)
                
            except Exception as e:
                logger.warning(f"⚠️ Не удалось выполнить действие {purpose}: {e}")
        
        success_rate = success_count / total_actions if total_actions > 0 else 0
        logger.info(f"📊 Выполнено действий: {success_count}/{total_actions} ({success_rate:.1%})")
        
        return success_rate >= 0.7  # Считаем успешным если выполнено 70%+ действий
    
    def _format_date(self, date_str: str) -> str:
        """Форматирует дату в нужный формат"""
        try:
            # Пробуем разные форматы даты
            from datetime import datetime
            
            # Если дата в формате DD.MM.YYYY
            if '.' in date_str:
                parts = date_str.split('.')
                if len(parts) == 3:
                    day, month, year = parts
                    return f"{month.zfill(2)}/{day.zfill(2)}/{year}"
            
            # Если дата в формате MM/DD/YYYY - возвращаем как есть
            if '/' in date_str:
                return date_str
            
            return date_str
            
        except Exception:
            return date_str