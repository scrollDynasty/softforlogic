import asyncio
import time
from datetime import datetime
from typing import Dict, Optional
import traceback

from telegram import Bot
from telegram.error import TelegramError

from ..utils.logger import logger

class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.bot = Bot(token=bot_token)
        self.last_notification_time = 0
        self.notification_count = 0
        self.hour_start_time = time.time()
        
    async def format_message(self, load_data: dict, analysis: dict) -> str:
        """Форматирование сообщения с эмодзи и детальной информацией"""
        profit_emoji = "🟢" if analysis.get('profitability_score', 0) > 2.0 else "🟡"
        urgency_emoji = "🚨" if analysis.get('profitability_score', 0) > 2.5 else "⚡️"
        
        # Форматирование даты pickup
        pickup_date = load_data.get('pickup_date', 'N/A')
        if pickup_date and pickup_date != 'N/A':
            try:
                # Попытка парсинга даты
                if isinstance(pickup_date, str):
                    pickup_date = pickup_date[:10]  # Берем только дату
            except:
                pickup_date = 'N/A'
        
        # Форматирование ставки
        rate = load_data.get('rate', 0)
        rate_formatted = f"${rate:,.2f}" if rate else "N/A"
        
        # Форматирование rate per mile
        rate_per_mile = analysis.get('rate_per_mile', 0)
        rate_per_mile_formatted = f"${rate_per_mile:.2f}" if rate_per_mile else "N/A"
        
        # Форматирование profit margin
        profit_margin = analysis.get('profit_margin', 0)
        profit_margin_formatted = f"${profit_margin:,.2f}" if profit_margin else "N/A"
        
        # Определение приоритета
        priority = analysis.get('priority', 'MEDIUM')
        priority_emoji = "🔴" if priority == "HIGH" else "🟡" if priority == "MEDIUM" else "🟢"
        
        message = f"""{urgency_emoji} NEW PROFITABLE LOAD {profit_emoji}

📦 **Load ID**: `{load_data.get('id', 'N/A')}`
📍 **Route**: {load_data.get('pickup', 'N/A')} → {load_data.get('delivery', 'N/A')}
🛣 **Total Miles**: {analysis.get('total_miles', 0):,} miles  
🚚 **Deadhead**: {load_data.get('deadhead', 0)} miles ({analysis.get('deadhead_ratio', 0):.1%})
💰 **Rate**: {rate_formatted} ({rate_per_mile_formatted}/mile)
💵 **Profit Margin**: {profit_margin_formatted}
⏰ **Pickup**: {pickup_date}
🚛 **Equipment**: {load_data.get('equipment', 'N/A')}

📊 **Profitability Score**: {analysis.get('profitability_score', 0):.2f}x
⚡️ **Found**: {datetime.now().strftime('%H:%M:%S')}
🎯 **Priority**: {priority_emoji} {priority}

🔗 [View Load Details]({load_data.get('url', '#')})"""
        
        return message
    
    async def send_notification(self, load_data: dict, analysis: dict) -> bool:
        """Отправка уведомления о прибыльном грузе"""
        try:
            # Проверка лимитов уведомлений
            if not await self._check_notification_limits():
                logger.warning("⚠️ Превышен лимит уведомлений")
                return False
            
            message = await self.format_message(load_data, analysis)
            
            # Отправка сообщения с retry логикой
            for attempt in range(3):
                try:
                    await self.bot.send_message(
                        chat_id=self.chat_id,
                        text=message,
                        parse_mode='Markdown',
                        disable_web_page_preview=True
                    )
                    
                    self.last_notification_time = time.time()
                    self.notification_count += 1
                    
                    logger.info(f"✅ Уведомление отправлено: {load_data.get('id', 'unknown')}")
                    return True
                    
                except TelegramError as e:
                    if attempt < 2:
                        logger.warning(f"⚠️ Попытка {attempt + 1} отправки уведомления не удалась: {e}")
                        await asyncio.sleep(1)
                    else:
                        raise e
                        
        except Exception as e:
            logger.error(f"❌ Ошибка отправки уведомления: {e}")
            return False
    
    async def send_error_alert(self, error_msg: str, screenshot_path: str = None) -> bool:
        """Отправка уведомления об ошибке"""
        try:
            message = f"""🚨 **SYSTEM ERROR ALERT**

❌ **Error**: {error_msg}
⏰ **Time**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
🔧 **Status**: Requires attention

Please check the system immediately!"""
            
            # Отправка текстового сообщения
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode='Markdown'
            )
            
            # Отправка скриншота если есть
            if screenshot_path:
                try:
                    with open(screenshot_path, 'rb') as photo:
                        await self.bot.send_photo(
                            chat_id=self.chat_id,
                            photo=photo,
                            caption="📸 Error Screenshot"
                        )
                except Exception as e:
                    logger.error(f"❌ Ошибка отправки скриншота: {e}")
            
            logger.info("✅ Уведомление об ошибке отправлено")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки уведомления об ошибке: {e}")
            return False
    
    async def send_status_update(self, status_msg: str) -> bool:
        """Отправка статуса системы"""
        try:
            message = f"""📊 **SYSTEM STATUS UPDATE**

{status_msg}

⏰ **Last Update**: {datetime.now().strftime('%H:%M:%S')}"""
            
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode='Markdown'
            )
            
            logger.info("✅ Статус системы отправлен")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки статуса: {e}")
            return False
    
    async def send_daily_report(self, stats: dict) -> bool:
        """Отправка ежедневного отчета"""
        try:
            # Форматирование статистики
            loads_sent = stats.get('loads_sent', 0)
            avg_profitability = stats.get('avg_profitability', 0)
            total_miles = stats.get('total_miles', 0)
            avg_scan_time = stats.get('avg_scan_time_ms', 0)
            total_errors = stats.get('total_errors', 0)
            
            # Эмодзи для статуса
            status_emoji = "🟢" if total_errors == 0 else "🟡" if total_errors < 5 else "🔴"
            
            message = f"""📈 **DAILY PERFORMANCE REPORT** {status_emoji}

📅 **Date**: {datetime.now().strftime('%Y-%m-%d')}

📦 **Loads Sent**: {loads_sent}
📊 **Avg Profitability**: {avg_profitability:.2f}x
🛣 **Total Miles**: {total_miles:,}
⚡️ **Avg Scan Time**: {avg_scan_time:.0f}ms
❌ **Total Errors**: {total_errors}

📈 **Performance Summary**:
• {'Excellent' if loads_sent > 10 else 'Good' if loads_sent > 5 else 'Fair'} day for loads
• {'High' if avg_profitability > 2.0 else 'Medium' if avg_profitability > 1.5 else 'Low'} profitability
• {'Fast' if avg_scan_time < 2000 else 'Normal' if avg_scan_time < 5000 else 'Slow'} scanning
• {'Stable' if total_errors == 0 else 'Some issues' if total_errors < 5 else 'Needs attention'} system

Keep up the great work! 🚀"""
            
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode='Markdown'
            )
            
            logger.info("✅ Ежедневный отчет отправлен")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки ежедневного отчета: {e}")
            return False
    
    async def send_performance_report(self, performance_data: dict) -> bool:
        """Отправка отчета о производительности"""
        try:
            operations = performance_data.get('operations', [])
            
            if not operations:
                message = "📊 **PERFORMANCE REPORT**: No data available"
            else:
                message = f"""📊 **PERFORMANCE REPORT** ({performance_data.get('period_hours', 24)}h)

"""
                
                for op in operations[:5]:  # Топ-5 операций
                    operation = op['operation']
                    avg_duration = op['avg_duration_ms']
                    success_rate = op['success_rate_percent']
                    count = op['count']
                    
                    # Эмодзи для производительности
                    perf_emoji = "🟢" if avg_duration < 1000 else "🟡" if avg_duration < 5000 else "🔴"
                    success_emoji = "🟢" if success_rate > 95 else "🟡" if success_rate > 80 else "🔴"
                    
                    message += f"""{perf_emoji} **{operation}**:
• Duration: {avg_duration:.0f}ms
• Success Rate: {success_emoji} {success_rate:.1f}%
• Count: {count}

"""
            
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode='Markdown'
            )
            
            logger.info("✅ Отчет о производительности отправлен")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки отчета о производительности: {e}")
            return False
    
    async def _check_notification_limits(self) -> bool:
        """Проверка лимитов уведомлений"""
        current_time = time.time()
        
        # Сброс счетчика каждый час
        if current_time - self.hour_start_time > 3600:
            self.notification_count = 0
            self.hour_start_time = current_time
        
        # Проверка минимального интервала между уведомлениями
        if current_time - self.last_notification_time < 5:  # 5 секунд
            return False
        
        # Проверка максимального количества уведомлений в час
        if self.notification_count >= 50:
            return False
        
        return True
    
    async def test_connection(self) -> bool:
        """Тест соединения с Telegram"""
        try:
            await self.bot.get_me()
            logger.info("✅ Соединение с Telegram установлено")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка соединения с Telegram: {e}")
            return False
