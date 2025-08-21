import re
from typing import Dict, Tuple, Optional
from dataclasses import dataclass

@dataclass
class ProfitabilityAnalysis:
    """Структура для анализа прибыльности груза"""
    total_miles: int
    rate_per_mile: float
    profit_margin: float
    profitability_score: float
    is_profitable: bool
    deadhead_ratio: float
    fuel_cost: float
    gross_profit: float
    net_profit_margin: float
    quality_score: int
    priority: str

class RateCalculator:
    """Калькулятор прибыльности грузов"""
    
    # Предкомпилированные регулярные выражения для скорости
    COMPILED_PATTERNS = {
        'price': re.compile(r'\$[\d,]+\.?\d*'),
        'miles': re.compile(r'(\d+)\s*mile'),
        'deadhead': re.compile(r'(\d+)\s*DH|(\d+)\s*Empty'),
        'rate_per_mile': re.compile(r'\$(\d+\.?\d*)/mile')
    }
    
    @staticmethod
    def extract_number_cached(text: str, pattern_name: str) -> Optional[float]:
        """Кешированное извлечение чисел с предкомпилированными паттернами"""
        if not text:
            return None
            
        pattern = RateCalculator.COMPILED_PATTERNS.get(pattern_name)
        if pattern:
            match = pattern.search(text)
            if match:
                # Извлекаем первое число из группы
                for group in match.groups():
                    if group:
                        return float(group.replace(',', ''))
        return None
    
    @staticmethod
    def calculate_minimum_rate(deadhead: int, miles: int, base_rate: float = 1.7) -> float:
        """Формула: (deadhead_miles + total_miles) * base_rate = minimum_acceptable_rate"""
        return (deadhead + miles) * base_rate
    
    @staticmethod
    def is_load_profitable(deadhead: int, miles: int, rate: float = None, 
                          min_profitability: float = 1.5) -> Tuple[bool, Dict]:
        """
        Возвращает (is_profitable, analysis_data)
        analysis_data содержит все расчеты для отчетности
        """
        if rate is None:
            rate = RateCalculator.calculate_minimum_rate(deadhead, miles)
        
        total_miles = deadhead + miles
        rate_per_mile = rate / total_miles if total_miles > 0 else 0
        profit_margin = (rate_per_mile - 1.7) * total_miles if total_miles > 0 else 0
        
        analysis = {
            'total_miles': total_miles,
            'rate_per_mile': rate_per_mile,
            'profit_margin': profit_margin,
            'profitability_score': rate_per_mile / min_profitability if min_profitability > 0 else 0,
            'is_profitable': rate_per_mile >= min_profitability,
            'deadhead_ratio': deadhead / total_miles if total_miles > 0 else 0
        }
        
        return analysis['is_profitable'], analysis
    
    @staticmethod
    def calculate_fuel_costs(total_miles: int, mpg: float = 6.5, fuel_price: float = 4.0) -> float:
        """Расчет затрат на топливо"""
        return (total_miles / mpg) * fuel_price
    
    @staticmethod
    def calculate_comprehensive_profitability(load_data: dict) -> ProfitabilityAnalysis:
        """Комплексный расчет прибыльности с учетом всех факторов"""
        deadhead = load_data.get('deadhead', 0)
        miles = load_data.get('miles', 0)
        rate = load_data.get('rate')
        
        # Базовые расчеты
        total_miles = deadhead + miles
        
        if rate is None:
            rate = (deadhead + miles) * 1.7  # Минимальная ставка
            
        rate_per_mile = rate / total_miles if total_miles > 0 else 0
        
        # Дополнительные факторы
        deadhead_ratio = deadhead / total_miles if total_miles > 0 else 0
        fuel_cost = RateCalculator.calculate_fuel_costs(total_miles)
        gross_profit = rate - fuel_cost
        net_profit_margin = (gross_profit / rate) * 100 if rate > 0 else 0
        
        # Оценка качества груза
        quality_score = RateCalculator._calculate_quality_score(
            rate_per_mile, deadhead_ratio, miles, load_data
        )
        
        # Определение приоритета
        priority = RateCalculator._determine_priority(quality_score, rate_per_mile)
        
        return ProfitabilityAnalysis(
            total_miles=total_miles,
            rate_per_mile=rate_per_mile,
            profit_margin=gross_profit,
            profitability_score=rate_per_mile / 1.5 if rate_per_mile > 0 else 0,
            is_profitable=rate_per_mile >= 1.5 and quality_score >= 3,
            deadhead_ratio=deadhead_ratio,
            fuel_cost=fuel_cost,
            gross_profit=gross_profit,
            net_profit_margin=net_profit_margin,
            quality_score=quality_score,
            priority=priority
        )
    
    @staticmethod
    def _calculate_quality_score(rate_per_mile: float, deadhead_ratio: float, 
                                miles: int, load_data: dict) -> int:
        """Расчет оценки качества груза"""
        quality_score = 0
        
        # Оценка по ставке за милю
        if rate_per_mile >= 2.0:
            quality_score += 3
        elif rate_per_mile >= 1.8:
            quality_score += 2
        elif rate_per_mile >= 1.5:
            quality_score += 1
            
        # Оценка по deadhead
        if deadhead_ratio <= 0.1:  # Менее 10% deadhead
            quality_score += 2
        elif deadhead_ratio <= 0.2:  # Менее 20% deadhead
            quality_score += 1
            
        # Оценка по расстоянию
        if miles >= 500:  # Длинные рейсы более выгодны
            quality_score += 1
        elif miles >= 200:  # Средние рейсы
            quality_score += 1
            
        # Оценка по типу оборудования
        equipment = load_data.get('equipment', '').lower()
        preferred_equipment = ['van', 'reefer', 'flatbed']
        if any(pref in equipment for pref in preferred_equipment):
            quality_score += 1
            
        # Оценка по срочности (если есть pickup_date)
        pickup_date = load_data.get('pickup_date')
        if pickup_date:
            # Логика оценки срочности может быть добавлена здесь
            quality_score += 1
            
        return quality_score
    
    @staticmethod
    def _determine_priority(quality_score: int, rate_per_mile: float) -> str:
        """Определение приоритета груза"""
        if quality_score >= 5 and rate_per_mile >= 2.0:
            return 'HIGH'
        elif quality_score >= 3 and rate_per_mile >= 1.5:
            return 'MEDIUM'
        else:
            return 'LOW'
    
    @staticmethod
    def parse_rate_from_text(text: str) -> Optional[float]:
        """Извлечение ставки из текста"""
        if not text:
            return None
            
        # Удаляем все символы кроме цифр, точек и запятых
        cleaned = re.sub(r'[^\d.,]', '', text)
        if not cleaned:
            return None
            
        # Заменяем запятые на точки для десятичных чисел
        cleaned = cleaned.replace(',', '')
        
        try:
            return float(cleaned)
        except ValueError:
            return None
    
    @staticmethod
    def parse_miles_from_text(text: str) -> Optional[int]:
        """Извлечение миль из текста"""
        if not text:
            return None
            
        # Ищем числа перед словом "mile" или "mi"
        match = re.search(r'(\d+)\s*(?:mile|mi)', text, re.IGNORECASE)
        if match:
            return int(match.group(1))
            
        # Ищем просто числа (может быть мили)
        numbers = re.findall(r'\d+', text)
        if numbers:
            # Берем первое число, если оно разумное для миль
            miles = int(numbers[0])
            if 10 <= miles <= 3000:  # Разумный диапазон для миль
                return miles
                
        return None
    
    @staticmethod
    def parse_deadhead_from_text(text: str) -> Optional[int]:
        """Извлечение deadhead из текста"""
        if not text:
            return None
            
        # Ищем "DH", "Deadhead", "Empty" с числами
        patterns = [
            r'(\d+)\s*DH',
            r'(\d+)\s*Deadhead',
            r'(\d+)\s*Empty',
            r'DH\s*(\d+)',
            r'Deadhead\s*(\d+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return int(match.group(1))
                
        return None
