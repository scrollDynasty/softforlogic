import asyncio
import json
import base64
import time
from typing import Dict, List, Optional, Any, Tuple
from playwright.async_api import Page, ElementHandle
import google.generativeai as genai
from ..utils.logger import logger

class SmartAINavigator:
    """
    🧠 Умный AI-навигатор для автоматического решения проблем навигации и взаимодействия с сайтом
    
    Возможности:
    - Анализ текущего состояния страницы
    - Принятие решений о следующих действиях
    - Автоматическое восстановление при ошибках
    - Адаптация к изменениям интерфейса
    - Обучение на основе опыта
    """
    
    def __init__(self, api_key: str):
        try:
            self.api_key = api_key
            logger.info(f"🔑 Инициализация Gemini с API ключом: {api_key[:10] if api_key else 'None'}...")
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel('gemini-2.5-flash')  # Используем более быструю модель
            logger.info("✅ Gemini модель инициализирована успешно")
            
            # История действий и результатов для обучения
            self.action_history = []
            self.success_patterns = {}
            self.failure_patterns = {}
            
            logger.info("🧠 Smart AI Navigator инициализирован")
            
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации Gemini: {e}")
            raise
    
    async def analyze_and_navigate(self, page: Page, goal: str, context: Dict = None) -> Dict[str, Any]:
        """
        Основной метод: анализирует ситуацию и выполняет навигацию к цели
        
        Args:
            page: Playwright страница
            goal: Цель навигации (например, "navigate_to_search_page")
            context: Дополнительный контекст (учетные данные, предыдущие ошибки и т.д.)
        
        Returns:
            Dict с результатом анализа и действий
        """
        start_time = time.time()
        
        try:
            logger.info(f"🧠 AI анализирует ситуацию для цели: {goal}")
            
            # 1. Анализ текущего состояния
            page_analysis = await self._analyze_current_state(page)
            
            # Проверяем, есть ли ошибка в анализе
            if 'error' in page_analysis:
                logger.error(f"❌ Ошибка анализа страницы: {page_analysis['error']}")
                return {
                    'success': False,
                    'error': f"Page analysis failed: {page_analysis['error']}",
                    'execution_time': time.time() - start_time
                }
            
            # 2. Определение стратегии действий
            strategy = await self._determine_strategy(page_analysis, goal, context)
            
            # Проверяем валидность стратегии
            if not strategy.get('actions'):
                logger.error("❌ AI не смог определить стратегию действий")
                return {
                    'success': False,
                    'error': 'No strategy determined by AI',
                    'execution_time': time.time() - start_time
                }
            
            # 3. Выполнение действий
            result = await self._execute_strategy(page, strategy, goal)
            
            # 4. Обучение на основе результата
            await self._learn_from_result(page_analysis, strategy, result, goal)
            
            execution_time = time.time() - start_time
            logger.info(f"⏱️ AI навигация завершена за {execution_time:.1f}с")
            
            return {
                'success': result.get('success', False),
                'actions_taken': result.get('actions', []),
                'analysis': page_analysis,
                'strategy': strategy,
                'execution_time': execution_time,
                'confidence': result.get('confidence', 0.5)
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка AI навигации: {e}")
            return {
                'success': False,
                'error': str(e),
                'execution_time': time.time() - start_time
            }
    
    async def _analyze_current_state(self, page: Page) -> Dict[str, Any]:
        """Анализирует текущее состояние страницы"""
        try:
            logger.info("📸 Получаю скриншот страницы...")
            
            # Проверяем состояние страницы
            try:
                page_url = page.url
                logger.info(f"📍 Текущий URL: {page_url}")
                
                # Проверяем, не закрыта ли страница
                is_closed = page.is_closed()
                if is_closed:
                    logger.error("❌ Страница закрыта, невозможно сделать скриншот")
                    return {'error': 'Page is closed'}
                    
            except Exception as e:
                logger.error(f"❌ Ошибка проверки состояния страницы: {e}")
                return {'error': f'Page state check failed: {str(e)}'}
            
            # Получаем скриншот и базовую информацию с таймаутом
            try:
                screenshot = await asyncio.wait_for(page.screenshot(), timeout=5.0)
                screenshot_b64 = base64.b64encode(screenshot).decode()
                logger.info(f"✅ Скриншот получен: {len(screenshot_b64)} символов")
            except asyncio.TimeoutError:
                logger.error("⏰ ТАЙМАУТ: Не удалось получить скриншот за 5 секунд")
                # Возвращаем пустой скриншот
                screenshot_b64 = ""
            except Exception as e:
                logger.error(f"❌ Ошибка получения скриншота: {e}")
                screenshot_b64 = ""
            
            # Собираем информацию о странице
            logger.info("📄 Собираю информацию о странице...")
            try:
                page_info = await asyncio.wait_for(page.evaluate("""
                () => {
                    return {
                        url: window.location.href,
                        title: document.title,
                        readyState: document.readyState,
                        visibleText: document.body?.innerText?.substring(0, 2000) || '',
                        forms: Array.from(document.forms).map(form => ({
                            action: form.action,
                            method: form.method,
                            elements: form.elements.length
                        })),
                        buttons: Array.from(document.querySelectorAll('button, input[type="submit"], input[type="button"]')).map(btn => ({
                            text: btn.textContent?.trim() || btn.value || '',
                            type: btn.type || btn.tagName,
                            visible: btn.offsetWidth > 0 && btn.offsetHeight > 0
                        })).filter(btn => btn.visible),
                        links: Array.from(document.querySelectorAll('a[href]')).map(link => ({
                            text: link.textContent?.trim() || '',
                            href: link.href,
                            visible: link.offsetWidth > 0 && link.offsetHeight > 0
                        })).filter(link => link.visible && link.text).slice(0, 20),
                        inputs: Array.from(document.querySelectorAll('input, select, textarea')).map(input => ({
                            type: input.type || input.tagName,
                            name: input.name || '',
                            placeholder: input.placeholder || '',
                            value: input.value || '',
                            visible: input.offsetWidth > 0 && input.offsetHeight > 0
                        })).filter(input => input.visible),
                        errors: Array.from(document.querySelectorAll('.error, .alert-danger, [class*="error"], [class*="warning"]')).map(el => el.textContent?.trim()).filter(text => text),
                        loading: document.querySelectorAll('.loading, .spinner, [class*="loading"], [class*="spinner"]').length > 0
                    }
                }
            """), timeout=5.0)
                logger.info("✅ Информация о странице получена")
            except asyncio.TimeoutError:
                logger.error("⏰ ТАЙМАУТ: Не удалось получить информацию о странице за 5 секунд")
                # Возвращаем базовую информацию
                page_info = {
                    'url': 'unknown',
                    'title': 'unknown',
                    'readyState': 'unknown',
                    'buttons': [],
                    'links': [],
                    'forms': [],
                    'inputs': [],
                    'errors': [],
                    'loading': False,
                    'visibleText': ''
                }
            
            # Создаем промпт для анализа состояния
            analysis_prompt = f"""
Проанализируй текущее состояние веб-страницы и определи:

ИНФОРМАЦИЯ О СТРАНИЦЕ:
URL: {page_info['url']}
Заголовок: {page_info['title']}
Состояние загрузки: {page_info['readyState']}

ЭЛЕМЕНТЫ ИНТЕРФЕЙСА:
Кнопки: {json.dumps(page_info['buttons'], ensure_ascii=False)}
Ссылки: {json.dumps(page_info['links'], ensure_ascii=False)}
Поля ввода: {json.dumps(page_info['inputs'], ensure_ascii=False)}
Формы: {json.dumps(page_info['forms'], ensure_ascii=False)}

ОШИБКИ: {page_info['errors']}
ЗАГРУЗКА: {page_info['loading']}

ВИДИМЫЙ ТЕКСТ (первые 2000 символов):
{page_info['visibleText']}

ЗАДАЧА: Определи текущее состояние страницы и возможные действия.

ОТВЕТЬ В ФОРМАТЕ JSON:
{{
    "page_type": "login_page|search_page|results_page|error_page|loading_page|unknown",
    "authentication_status": "logged_in|logged_out|2fa_required|session_expired|unknown",
    "available_actions": ["navigate_to_search", "fill_form", "click_button", "wait_for_load", etc.],
    "blocking_issues": ["captcha", "2fa_required", "session_expired", "page_not_loaded", etc.],
    "confidence": 0.95,
    "next_recommended_action": "описание рекомендуемого действия",
    "context_clues": ["список ключевых элементов, которые помогли в анализе"]
}}
"""
            
            # Получаем анализ от AI
            try:
                logger.info("🤖 Подготовка запроса к Gemini AI...")
                logger.info(f"📝 Размер промпта: {len(analysis_prompt)} символов")
                ai_response = await self._get_ai_response(analysis_prompt, screenshot_b64)
                logger.info(f"📨 Получен ответ от AI: {len(ai_response) if ai_response else 0} символов")
                ai_analysis = self._parse_json_response(ai_response)
                
                return {
                    'page_info': page_info,
                    'ai_analysis': ai_analysis,
                    'screenshot_b64': screenshot_b64,
                    'timestamp': time.time()
                }
                
            except Exception as ai_error:
                logger.error(f"❌ Ошибка получения ответа от AI: {ai_error}")
                return {'error': f'AI response error: {str(ai_error)}'}
            
        except Exception as e:
            logger.error(f"❌ Ошибка анализа состояния: {e}")
            return {'error': str(e)}
    
    async def _determine_strategy(self, analysis: Dict, goal: str, context: Dict = None) -> Dict[str, Any]:
        """Определяет стратегию действий на основе анализа"""
        try:
            ai_analysis = analysis.get('ai_analysis', {})
            page_info = analysis.get('page_info', {})
            
            # Создаем промпт для определения стратегии
            strategy_prompt = f"""
Ты - эксперт по автоматизации веб-навигации. Определи оптимальную стратегию для достижения цели.

ЦЕЛЬ: {goal}

ТЕКУЩЕЕ СОСТОЯНИЕ:
{json.dumps(ai_analysis, indent=2, ensure_ascii=False)}

ДОПОЛНИТЕЛЬНЫЙ КОНТЕКСТ:
{json.dumps(context or {}, indent=2, ensure_ascii=False)}

ИСТОРИЯ УСПЕШНЫХ ДЕЙСТВИЙ:
{json.dumps(self.success_patterns.get(goal, []), indent=2, ensure_ascii=False)}

ИСТОРИЯ НЕУДАЧНЫХ ДЕЙСТВИЙ:
{json.dumps(self.failure_patterns.get(goal, []), indent=2, ensure_ascii=False)}

ЗАДАЧА: Создай детальную стратегию с конкретными действиями.

ОТВЕТЬ В ФОРМАТЕ JSON:
{{
    "strategy_type": "direct_navigation|form_filling|error_recovery|wait_and_retry|multi_step",
    "confidence": 0.9,
    "estimated_time": 15,
    "actions": [
        {{
            "step": 1,
            "action": "goto_url|click_element|fill_input|wait_for_element|take_screenshot",
            "target": "селектор или URL",
            "value": "значение если нужно",
            "timeout": 10,
            "fallback_action": "что делать если не сработает",
            "success_indicator": "как понять что действие выполнено",
            "description": "человекочитаемое описание действия"
        }}
    ],
    "fallback_strategy": "что делать если основная стратегия не сработает",
    "risk_factors": ["список потенциальных проблем"],
    "success_probability": 0.85
}}
"""
            
            try:
                ai_response = await self._get_ai_response(strategy_prompt, analysis.get('screenshot_b64'))
                strategy = self._parse_json_response(ai_response)
                
                logger.info(f"🎯 AI выбрал стратегию: {strategy.get('strategy_type')} (уверенность: {strategy.get('confidence', 0):.1%})")
                
                return strategy
                
            except Exception as ai_error:
                logger.error(f"❌ Ошибка получения стратегии от AI: {ai_error}")
                return {'strategy_type': 'error', 'actions': [], 'error': str(ai_error)}
            
        except Exception as e:
            logger.error(f"❌ Ошибка определения стратегии: {e}")
            return {'strategy_type': 'error', 'actions': [], 'error': str(e)}
    
    async def _execute_strategy(self, page: Page, strategy: Dict, goal: str) -> Dict[str, Any]:
        """Выполняет стратегию действий"""
        executed_actions = []
        success = True
        
        try:
            actions = strategy.get('actions', [])
            logger.info(f"🚀 Выполняю стратегию из {len(actions)} шагов")
            
            for action in actions:
                step = action.get('step', 0)
                action_type = action.get('action')
                target = action.get('target')
                value = action.get('value')
                timeout = action.get('timeout', 3) * 1000  # Сокращен таймаут с 10 до 3 секунд
                description = action.get('description', f"Шаг {step}")
                
                logger.info(f"🎯 Шаг {step}: {description}")
                
                try:
                    action_start = time.time()
                    action_result = await self._execute_single_action(page, action_type, target, value, timeout)
                    action_time = time.time() - action_start
                    
                    executed_actions.append({
                        'step': step,
                        'action': action_type,
                        'target': target,
                        'success': action_result,
                        'time': action_time,
                        'description': description
                    })
                    
                    if action_result:
                        logger.info(f"✅ Шаг {step} выполнен успешно ({action_time:.1f}с)")
                        
                        # Проверяем индикатор успеха если указан
                        success_indicator = action.get('success_indicator')
                        if success_indicator:
                            await self._verify_action_success(page, success_indicator)
                    else:
                        logger.warning(f"⚠️ Шаг {step} не выполнен")
                        
                        # Пробуем fallback действие
                        fallback = action.get('fallback_action')
                        if fallback:
                            logger.info(f"🔄 Пробую fallback: {fallback}")
                            # Здесь можно реализовать выполнение fallback действия
                        
                        success = False
                        break
                    
                    # Убрана избыточная пауза между действиями
                    
                except Exception as e:
                    logger.error(f"❌ Ошибка выполнения шага {step}: {e}")
                    executed_actions.append({
                        'step': step,
                        'action': action_type,
                        'success': False,
                        'error': str(e)
                    })
                    success = False
                    break
            
            return {
                'success': success,
                'actions': executed_actions,
                'confidence': strategy.get('confidence', 0.5) if success else 0.1
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка выполнения стратегии: {e}")
            return {
                'success': False,
                'actions': executed_actions,
                'error': str(e),
                'confidence': 0.1
            }
    
    async def _execute_single_action(self, page: Page, action_type: str, target: str, value: Any, timeout: int) -> bool:
        """Выполняет одно действие"""
        try:
            if action_type == 'goto_url':
                await page.goto(target, wait_until='domcontentloaded', timeout=timeout)
                return True
                
            elif action_type == 'click_element':
                element = await page.wait_for_selector(target, timeout=timeout)
                if element:
                    await element.click()
                    return True
                    
            elif action_type == 'fill_input':
                element = await page.wait_for_selector(target, timeout=timeout)
                if element:
                    await element.clear()
                    await element.fill(str(value))
                    return True
                    
            elif action_type == 'select_option':
                element = await page.wait_for_selector(target, timeout=timeout)
                if element:
                    await element.select_option(label=str(value))
                    return True
                    
            elif action_type == 'wait_for_element':
                element = await page.wait_for_selector(target, timeout=timeout)
                return element is not None
                
            elif action_type == 'wait_for_load':
                await page.wait_for_load_state('domcontentloaded', timeout=timeout)
                return True
                
            elif action_type == 'take_screenshot':
                await page.screenshot(path=f"debug_screenshot_{int(time.time())}.png")
                return True
                
            return False
            
        except Exception as e:
            logger.error(f"❌ Ошибка выполнения действия {action_type}: {e}")
            return False
    
    async def _verify_action_success(self, page: Page, success_indicator: str) -> bool:
        """Проверяет успешность выполнения действия"""
        try:
            # Можно проверить URL, наличие элементов, текст и т.д.
            if success_indicator.startswith('url_contains:'):
                expected_url_part = success_indicator.replace('url_contains:', '')
                current_url = page.url
                return expected_url_part in current_url
                
            elif success_indicator.startswith('element_exists:'):
                selector = success_indicator.replace('element_exists:', '')
                element = await page.query_selector(selector)
                return element is not None
                
            elif success_indicator.startswith('text_contains:'):
                expected_text = success_indicator.replace('text_contains:', '')
                page_text = await page.text_content('body')
                return expected_text in page_text
                
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки успеха: {e}")
            return False
    
    async def _learn_from_result(self, analysis: Dict, strategy: Dict, result: Dict, goal: str):
        """Обучается на основе результата выполнения"""
        try:
            # Сохраняем результат в историю
            learning_entry = {
                'timestamp': time.time(),
                'goal': goal,
                'page_type': analysis.get('ai_analysis', {}).get('page_type'),
                'strategy_type': strategy.get('strategy_type'),
                'success': result.get('success', False),
                'confidence': result.get('confidence', 0),
                'actions': result.get('actions', [])
            }
            
            self.action_history.append(learning_entry)
            
            # Обновляем паттерны успеха/неудач
            if result.get('success'):
                if goal not in self.success_patterns:
                    self.success_patterns[goal] = []
                self.success_patterns[goal].append({
                    'strategy': strategy,
                    'context': analysis.get('ai_analysis', {}),
                    'confidence': result.get('confidence', 0)
                })
                # Оставляем только последние 10 успешных паттернов
                self.success_patterns[goal] = self.success_patterns[goal][-10:]
            else:
                if goal not in self.failure_patterns:
                    self.failure_patterns[goal] = []
                self.failure_patterns[goal].append({
                    'strategy': strategy,
                    'context': analysis.get('ai_analysis', {}),
                    'error': result.get('error')
                })
                self.failure_patterns[goal] = self.failure_patterns[goal][-10:]
            
            logger.info(f"📚 AI обновил базу знаний для цели '{goal}'")
            
        except Exception as e:
            logger.error(f"❌ Ошибка обучения: {e}")
    
    async def _get_ai_response(self, prompt: str, screenshot_b64: str = None) -> str:
        """Получает ответ от AI с таймаутом"""
        try:
            content = [prompt]
            
            if screenshot_b64:
                content.append({
                    'mime_type': 'image/png',
                    'data': screenshot_b64
                })
            
            # Добавляем таймаут 30 секунд для запроса к AI
            logger.info("🤖 Отправляю запрос к Gemini AI...")
            start_time = time.time()
            
            # Используем asyncio.wait_for для таймаута
            import asyncio
            
            # Создаем асинхронную обертку для синхронного вызова
            async def generate_content_async():
                return await asyncio.get_event_loop().run_in_executor(
                    None, 
                    self.model.generate_content,
                    content
                )
            
            try:
                response = await asyncio.wait_for(generate_content_async(), timeout=15.0)
                elapsed = time.time() - start_time
                logger.info(f"✅ Получен ответ от AI за {elapsed:.1f}с")
                return response.text
                
            except asyncio.TimeoutError:
                elapsed = time.time() - start_time
                logger.error(f"⏰ ТАЙМАУТ: AI не ответил за {elapsed:.1f}с")
                raise Exception("AI request timeout after 15 seconds")
            
        except Exception as e:
            logger.error(f"❌ Ошибка запроса к AI: {e}")
            raise  # Пробрасываем ошибку дальше для обработки
    
    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        """Парсит JSON ответ от AI"""
        try:
            # Ищем JSON в ответе
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            
            if json_start != -1 and json_end != -1:
                json_str = response[json_start:json_end]
                return json.loads(json_str)
            
            logger.warning("⚠️ Не удалось найти JSON в ответе AI")
            return {}
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ Ошибка парсинга JSON: {e}")
            return {}
    
    def get_learning_stats(self) -> Dict[str, Any]:
        """Возвращает статистику обучения"""
        total_actions = len(self.action_history)
        successful_actions = sum(1 for action in self.action_history if action['success'])
        
        return {
            'total_actions': total_actions,
            'successful_actions': successful_actions,
            'success_rate': successful_actions / total_actions if total_actions > 0 else 0,
            'learned_goals': list(self.success_patterns.keys()),
            'success_patterns_count': sum(len(patterns) for patterns in self.success_patterns.values()),
            'failure_patterns_count': sum(len(patterns) for patterns in self.failure_patterns.values())
        }