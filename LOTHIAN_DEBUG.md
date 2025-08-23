# Руководство по диагностике LOTHIAN

## Проблема
Расширение показывает "Неизвестно" для всех полей данных на сайте LOTHIAN.

## Исправления
1. **Добавлены специальные селекторы для LOTHIAN**
2. **Создана отдельная функция парсинга для LOTHIAN**
3. **Улучшена система логирования**

## Как проверить что исправления работают

### 1. Откройте консоль браузера (F12)

### 2. Запустите отладочный отчет:
```javascript
freightDebugReport()
```

### 3. Протестируйте парсинг LOTHIAN:
```javascript
testLothianParsing()
```

### 4. Проверьте тип сайта:
```javascript
console.log('Тип сайта:', window.location.href.toLowerCase().includes('lothian') ? 'LOTHIAN' : 'Другой')
```

## Что должно работать после исправлений

### Для данных типа:
```
4007568993
Power Only
29 miles
43,373 lbs
IRVING, TX → LANCASTER, TX
$1,553
Deadhead 20 mi
```

### Ожидаемый результат:
- **ID груза**: 4007568993
- **Тип**: Power Only  
- **Откуда**: IRVING, TX
- **Куда**: LANCASTER, TX
- **Мили**: 29
- **Ставка**: $1,553 (если указана)
- **Deadhead**: 20 mi

## CSS классы для F12 диагностики

Если парсинг все еще не работает, найдите правильные CSS селекторы:

### 1. Откройте инспектор элементов (F12)
### 2. Найдите элемент с данными груза
### 3. Скопируйте CSS селектор (ПКМ → Copy → Copy selector)
### 4. Добавьте в SELECTORS в content.js

### Пример полезных селекторов:
```css
/* Строки таблицы */
table tbody tr
tr[role="row"]
.react-bootstrap-table tbody tr

/* ID груза */
td:nth-child(1)
td:first-child

/* Локации */
td:contains("TX")
td:contains(",")

/* Мили */
td:contains("miles")

/* Ставка */
td:contains("$")

/* Deadhead */
td:contains("Deadhead")
```

## Отладка в реальном времени

### Выполните в консоли:
```javascript
// Найти все элементы грузов
const elements = document.querySelectorAll('table tbody tr, tr[role="row"]');
console.log('Найдено элементов:', elements.length);

// Посмотреть содержимое первого элемента
if (elements.length > 0) {
  console.log('Первый элемент:', elements[0]);
  console.log('Текст:', elements[0].textContent);
}
```

## Если ничего не помогает

1. Сделайте скриншот страницы LOTHIAN
2. Откройте F12 → Elements  
3. Найдите элемент с данными груза
4. ПКМ → Copy → Copy outerHTML
5. Отправьте HTML разработчику для анализа