// FreightPower Load Monitor - Content Script

// Селекторы для парсинга (обновленные для FreightPower)
const SELECTORS = {
  load_items: [
    // Карточки грузов
    '[class*="card"][class*="load"]',
    '[class*="load-card"]',
    '[class*="freight-card"]',
    '[class*="search-result-card"]',
    '[class*="result-item"]',
    'div[class*="load"][class*="item"]',
    'article[class*="load"]',
    '.card',
    // Таблицы с грузами
    '[data-testid="load-row"]',
    '.load-item, .freight-item',
    'tr[class*="load"], tbody tr',
    '.search-results tr',
    '[class*="row"][class*="load"]',
    'table tbody tr'
  ],
  // Селекторы для полей внутри карточек
  load_id: [
    '[data-testid="reference"]',
    '[class*="reference-number"]',
    '[class*="load-number"]',
    '[class*="load-id"]',
    '.reference',
    '.load-reference, .id-column',
    'td:first-child',
    '[class*="id"]',
    '[class*="reference"]'
  ],
  capacity_type: [
    '[class*="capacity-type"]',
    '[class*="equipment-type"]',
    'label:contains("Capacity Type") ~ *',
    '*:contains("Capacity Type") + *',
    '[class*="type"]'
  ],
  pickup_location: [
    '[class*="origin"]',
    '[class*="pickup"]',
    'label:contains("Origin") ~ *',
    '*:contains("Origin") + *',
    '[data-testid="pickup-location"]',
    '.origin, .pickup, .pickup-location',
    'td:nth-child(2)'
  ],
  delivery_location: [
    '[class*="destination"]',
    '[class*="delivery"]',
    'label:contains("Destination") ~ *',
    '*:contains("Destination") + *',
    '[data-testid="delivery-location"]',
    '.destination, .delivery, .delivery-location',
    'td:nth-child(3)'
  ],
  pickup_date: [
    '[class*="pickup-date"]',
    '[class*="origin-date"]',
    'label:contains("Origin") ~ * [class*="date"]',
    '[class*="start-date"]'
  ],
  delivery_date: [
    '[class*="delivery-date"]',
    '[class*="destination-date"]',
    'label:contains("Destination") ~ * [class*="date"]',
    '[class*="end-date"]'
  ],
  miles: [
    '[class*="miles"]',
    '[class*="distance"]',
    'label:contains("Miles") ~ *',
    '*:contains("Miles") + *',
    '[data-testid="miles"]',
    '.distance, .total-miles, .miles-column',
    'td:nth-child(4)'
  ],
  deadhead: [
    '[class*="deadhead"]',
    '[class*="empty-miles"]',
    'label:contains("Deadhead") ~ *',
    '[data-testid="deadhead"]',
    '.deadhead, .empty-miles',
    'td:nth-child(5)'
  ],
  rate: [
    '[class*="rate"]',
    '[class*="price"]',
    '[class*="pay"]',
    'label:contains("Rate") ~ *',
    '*:contains("$")',
    '[data-testid="rate"]',
    '.rate, .price, .pay, .freight-rate',
    'td:nth-child(6)'
  ],
  radius: [
    '[class*="radius"]',
    '*:contains("mi")',
    'select[class*="radius"]',
    'input[type="range"]'
  ]
};

// Состояние мониторинга
let monitoringState = {
  isActive: false,
  isLoggedIn: false,
  scanInterval: null,
  settings: null,
  foundLoads: new Map(), // Кеш найденных грузов для избежания дубликатов
  lastScanTime: 0,
  scanCount: 0,
  adaptiveInterval: 3000,
  pendingScan: false // Флаг для отслеживания ожидающих сканирований
};

// Инициализация при загрузке
(function initialize() {
  console.log('FreightPower Load Monitor content script loaded');
  
  // Проверяем авторизацию при загрузке
  checkLoginStatus();
  
  // Слушаем сообщения от background script
  chrome.runtime.onMessage.addListener(handleMessage);
  
  // Периодически проверяем авторизацию
  setInterval(checkLoginStatus, 5000);
  
  // Наблюдаем за изменениями DOM
  observePageChanges();
})();

// Детекция успешной авторизации (синхронизирована с background.js)
function detectLogin() {
  // Проверяем URL
  const isOnFreightPower = window.location.href.includes('freightpower.schneider.com');
  const notOnLoginPage = !window.location.href.includes('/login') && !window.location.href.includes('/signin');
  
  if (!isOnFreightPower || !notOnLoginPage) {
    return false;
  }
  
  // Проверяем наличие элементов авторизованного пользователя
  const authIndicators = [
    document.querySelector('[data-user-authenticated]'),
    document.querySelector('.dashboard'),
    document.querySelector('.user-menu'),
    document.querySelector('.header-user'),
    document.querySelector('[class*="user-nav"]'),
    document.querySelector('[class*="profile"]'),
    document.querySelector('nav[class*="user"]'),
    document.querySelector('[class*="logged-in"]'),
    document.querySelector('[class*="authenticated"]')
  ];
  
  const hasAuthElement = authIndicators.some(el => el !== null);
  
  // Проверяем storage и cookies
  const hasAuthStorage = localStorage.getItem('userToken') || 
                        sessionStorage.getItem('authToken') ||
                        localStorage.getItem('auth') ||
                        sessionStorage.getItem('auth');
  
  const hasAuthCookie = document.cookie.includes('auth') || 
                       document.cookie.includes('session') ||
                       document.cookie.includes('token');
  
  // Проверяем наличие основных элементов страницы поиска
  const hasSearchElements = document.querySelector('.search-results') ||
                          document.querySelector('[class*="search"]') ||
                          document.querySelector('[class*="load"]') ||
                          document.querySelector('main');
  
  // Считаем пользователя авторизованным, если выполнено несколько условий
  const isLoggedIn = isOnFreightPower && notOnLoginPage && 
                    (hasAuthElement || hasAuthStorage || hasAuthCookie || hasSearchElements);
  
  console.log('Login check:', {
    isOnFreightPower,
    notOnLoginPage,
    hasAuthElement,
    hasAuthStorage,
    hasAuthCookie,
    hasSearchElements,
    result: isLoggedIn
  });
  
  return isLoggedIn;
}

// Проверка статуса авторизации
function checkLoginStatus() {
  const wasLoggedIn = monitoringState.isLoggedIn;
  monitoringState.isLoggedIn = detectLogin();
  
  // Если статус изменился
  if (wasLoggedIn !== monitoringState.isLoggedIn) {
    if (monitoringState.isLoggedIn) {
      console.log('✅ User logged in to FreightPower');
      chrome.runtime.sendMessage({ 
        type: 'LOGIN_DETECTED',
        url: window.location.href
      });
    } else {
      console.log('🔒 User logged out from FreightPower');
      chrome.runtime.sendMessage({ type: 'LOGOUT_DETECTED' });
      stopMonitoring();
    }
  }
}

// Обработка сообщений от background script
function handleMessage(message, sender, sendResponse) {
  console.log('Received message:', message.type);
  
  switch (message.type) {
    case 'START_MONITORING':
      if (!monitoringState.isActive && monitoringState.isLoggedIn) {
        startMonitoring(message.settings);
        sendResponse({ success: true });
      } else {
        sendResponse({ 
          success: false, 
          reason: monitoringState.isLoggedIn ? 'Already monitoring' : 'Not logged in' 
        });
      }
      break;
      
    case 'STOP_MONITORING':
      stopMonitoring();
      sendResponse({ success: true });
      break;
      
    case 'GET_STATUS':
      sendResponse({
        isActive: monitoringState.isActive,
        isLoggedIn: monitoringState.isLoggedIn,
        scanCount: monitoringState.scanCount,
        foundLoads: monitoringState.foundLoads.size
      });
      break;
      
    case 'PLAY_SOUND':
      playAlertSound();
      sendResponse({ success: true });
      break;
      
    case 'FORCE_SCAN':
      if (monitoringState.isActive) {
        scanForLoads();
        sendResponse({ success: true });
      } else {
        sendResponse({ success: false, reason: 'Monitoring not active' });
      }
      break;
      
    default:
      console.warn('Unknown message type:', message.type);
      sendResponse({ success: false, reason: 'Unknown message type' });
  }
  
  return true; // Указывает, что ответ может быть асинхронным
}

// Запуск мониторинга
function startMonitoring(settings) {
  if (monitoringState.isActive) {
    console.log('Monitoring already active');
    return;
  }
  
  if (!monitoringState.isLoggedIn) {
    console.log('Cannot start monitoring: not logged in');
    return;
  }
  
  monitoringState.settings = settings || {};
  monitoringState.isActive = true;
  monitoringState.scanCount = 0;
  monitoringState.foundLoads.clear();
  
  console.log('Starting automatic load monitoring...');
  
  // Запускаем первое сканирование сразу
  scanForLoads();
  
  // Устанавливаем интервал для регулярного сканирования
  monitoringState.scanInterval = setInterval(() => {
    scanForLoads();
  }, monitoringState.adaptiveInterval);
  
  // Показываем индикатор активности
  showMonitoringIndicator();
}

// Остановка мониторинга
function stopMonitoring() {
  if (!monitoringState.isActive) {
    return;
  }
  
  monitoringState.isActive = false;
  
  if (monitoringState.scanInterval) {
    clearInterval(monitoringState.scanInterval);
    monitoringState.scanInterval = null;
  }
  
  hideMonitoringIndicator();
  
  console.log('Load monitoring stopped');
}

// Перезапуск мониторинга с новыми настройками
function restartMonitoring() {
  if (monitoringState.isActive) {
    const settings = monitoringState.settings;
    stopMonitoring();
    setTimeout(() => startMonitoring(settings), 1000);
  }
}

// Основная функция сканирования грузов
function scanForLoads() {
  if (!monitoringState.isActive || !monitoringState.isLoggedIn) {
    return;
  }
  
  const startTime = Date.now();
  monitoringState.scanCount++;
  
  console.log(`Scanning for loads... (scan #${monitoringState.scanCount})`);
  
  try {
    const loadElements = findLoadElements();
    
    if (loadElements.length === 0) {
      console.log('No load elements found on page');
      adjustScanInterval('no_loads');
      return;
    }
    
    console.log(`Found ${loadElements.length} load elements`);
    
    let newLoadsFound = 0;
    let profitableLoadsFound = 0;
    
    loadElements.forEach((element, index) => {
      try {
        const loadData = parseLoadElement(element);
        
        if (loadData && loadData.id && !monitoringState.foundLoads.has(loadData.id)) {
          // Новый груз найден
          monitoringState.foundLoads.set(loadData.id, {
            ...loadData,
            foundAt: Date.now(),
            scanNumber: monitoringState.scanCount
          });
          
          newLoadsFound++;
          
          // Рассчитываем прибыльность
          const profitability = calculateProfitability(loadData);
          
          if (profitability.isProfitable && passesFilters(loadData, profitability)) {
            profitableLoadsFound++;
            
            // Отправляем найденный груз в background script
            chrome.runtime.sendMessage({
              type: 'LOAD_FOUND',
              data: {
                ...loadData,
                ...profitability,
                foundAt: Date.now(),
                scanNumber: monitoringState.scanCount
              }
            });
            
            console.log(`💰 Profitable load found: ${loadData.id} - $${profitability.ratePerMile.toFixed(2)}/mile`);
          }
        }
      } catch (error) {
        console.error(`Error parsing load element ${index}:`, error);
      }
    });
    
    // Обновляем статистику
    chrome.runtime.sendMessage({
      type: 'UPDATE_STATISTICS',
      data: {
        totalScans: 1,
        loadsFound: newLoadsFound,
        profitableLoads: profitableLoadsFound,
        lastActive: Date.now()
      }
    });
    
    // Адаптируем интервал сканирования
    if (newLoadsFound > 0) {
      adjustScanInterval('loads_found');
    } else {
      adjustScanInterval('no_new_loads');
    }
    
    const scanDuration = Date.now() - startTime;
    console.log(`Scan completed in ${scanDuration}ms. New loads: ${newLoadsFound}, Profitable: ${profitableLoadsFound}`);
    
  } catch (error) {
    console.error('Error during load scanning:', error);
    adjustScanInterval('error');
  }
  
  monitoringState.lastScanTime = Date.now();
}

// Поиск элементов грузов на странице
function findLoadElements() {
  console.log('🔍 Searching for load elements...');
  
  // Сначала пробуем найти контейнер с результатами поиска
  const searchContainers = [
    '.search-results',
    '[class*="search-result"]',
    '[class*="result-container"]',
    '[class*="load-list"]',
    '[class*="freight-list"]',
    'main [class*="container"]',
    '[role="main"]',
    '#app main',
    '.content-area'
  ];
  
  let container = document.body;
  for (const selector of searchContainers) {
    const found = document.querySelector(selector);
    if (found) {
      container = found;
      console.log(`📦 Found search container: ${selector}`);
      break;
    }
  }
  
  // Ищем элементы грузов
  for (const selector of SELECTORS.load_items) {
    const elements = container.querySelectorAll(selector);
    if (elements.length > 0) {
      console.log(`✅ Found ${elements.length} load elements using selector: ${selector}`);
      
      // Проверяем, что это действительно карточки грузов
      const validElements = Array.from(elements).filter(el => {
        // Элемент должен содержать хотя бы Origin или Destination
        const text = el.textContent || '';
        const hasLocation = text.includes('Origin') || text.includes('Destination') || 
                          text.includes(', ') || // Города обычно через запятую
                          /[A-Z]{2}\s*\d{5}/.test(text); // ZIP коды
        
        // Элемент должен быть достаточно большим (не пустым)
        const hasContent = el.childElementCount > 0 || text.length > 20;
        
        return hasLocation && hasContent;
      });
      
      if (validElements.length > 0) {
        console.log(`✅ Validated ${validElements.length} load elements`);
        return validElements;
      }
    }
  }
  
  // Если не нашли по селекторам, пробуем эвристический поиск
  console.log('⚠️ No elements found with selectors, trying heuristic search...');
  
  const allElements = container.querySelectorAll('div, article, section, tr');
  const potentialLoads = Array.from(allElements).filter(el => {
    const text = el.textContent || '';
    
    // Проверяем наличие ключевых слов
    const hasOrigin = text.includes('Origin') || /\b[A-Z][a-z]+(?:ville|ton|burg|city|town)\b/.test(text);
    const hasDestination = text.includes('Destination') || text.split(',').length > 2;
    const hasState = /\b[A-Z]{2}\b/.test(text);
    const hasMiles = /\b\d+\s*mi/i.test(text) || text.includes('miles');
    const hasDate = /\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}/i.test(text);
    
    // Элемент должен содержать несколько признаков груза
    const score = [hasOrigin, hasDestination, hasState, hasMiles, hasDate].filter(Boolean).length;
    
    return score >= 2 && el.childElementCount > 2;
  });
  
  if (potentialLoads.length > 0) {
    console.log(`🔍 Found ${potentialLoads.length} potential load elements through heuristic search`);
    return potentialLoads;
  }
  
  console.log('❌ No load elements found on page');
  return [];
}

// Парсинг данных груза из элемента
function parseLoadElement(element) {
  const loadData = {
    id: null,
    capacityType: null,
    pickup: null,
    delivery: null,
    pickupDate: null,
    deliveryDate: null,
    miles: 0,
    deadhead: 0,
    rate: 0,
    originRadius: null,
    destinationRadius: null,
    element: element
  };
  
  // Извлекаем ID груза
  loadData.id = extractText(element, SELECTORS.load_id) || generateLoadId(element);
  
  // Извлекаем тип груза
  loadData.capacityType = extractText(element, SELECTORS.capacity_type);
  
  // Извлекаем место погрузки
  loadData.pickup = extractText(element, SELECTORS.pickup_location);
  
  // Извлекаем место разгрузки
  loadData.delivery = extractText(element, SELECTORS.delivery_location);
  
  // Извлекаем даты
  loadData.pickupDate = extractText(element, SELECTORS.pickup_date);
  loadData.deliveryDate = extractText(element, SELECTORS.delivery_date);
  
  // Извлекаем мили
  const milesText = extractText(element, SELECTORS.miles);
  loadData.miles = parseNumber(milesText);
  
  // Извлекаем deadhead
  const deadheadText = extractText(element, SELECTORS.deadhead);
  loadData.deadhead = parseNumber(deadheadText);
  
  // Извлекаем ставку
  const rateText = extractText(element, SELECTORS.rate);
  loadData.rate = parseNumber(rateText);
  
  // Извлекаем радиусы
  const radiusElements = element.querySelectorAll(SELECTORS.radius.join(', '));
  if (radiusElements.length >= 2) {
    loadData.originRadius = extractRadius(radiusElements[0]);
    loadData.destinationRadius = extractRadius(radiusElements[1]);
  }
  
  // Валидация данных - теперь проверяем обязательные поля
  if (!loadData.pickup || !loadData.delivery) {
    console.warn('Missing pickup or delivery location:', loadData);
    return null;
  }
  
  // Если нет ID, генерируем уникальный на основе данных
  if (!loadData.id) {
    loadData.id = generateLoadId(loadData);
  }
  
  return loadData;
}

// Генерация уникального ID для груза
function generateLoadId(data) {
  if (data.pickup && data.delivery) {
    return `${data.pickup}-${data.delivery}-${Date.now()}`.replace(/\s+/g, '-');
  }
  return `load-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}

// Извлечение радиуса из элемента
function extractRadius(element) {
  if (!element) return null;
  
  const text = element.textContent || element.value || '';
  const match = text.match(/(\d+)\s*mi/i);
  return match ? parseInt(match[1]) : null;
}

// Извлечение текста из элемента по селекторам
function extractText(parentElement, selectors) {
  for (const selector of selectors) {
    try {
      let elements = [];
      
      // Обработка специальных селекторов
      if (selector.includes(':contains(')) {
        // Парсим селектор с :contains()
        const match = selector.match(/(.*):\contains\("([^"]+)"\)(.*)/);
        if (match) {
          const [, prefix, text, suffix] = match;
          const baseSelector = prefix || '*';
          const candidates = parentElement.querySelectorAll(baseSelector);
          
          for (const el of candidates) {
            if (el.textContent && el.textContent.includes(text)) {
              if (suffix) {
                // Если есть суффикс (например, ~ * или + *), ищем соседние элементы
                if (suffix.trim() === '~ *') {
                  // Следующие соседние элементы
                  let sibling = el.nextElementSibling;
                  while (sibling) {
                    elements.push(sibling);
                    sibling = sibling.nextElementSibling;
                  }
                } else if (suffix.trim() === '+ *') {
                  // Непосредственно следующий элемент
                  if (el.nextElementSibling) {
                    elements.push(el.nextElementSibling);
                  }
                }
              } else {
                elements.push(el);
              }
            }
          }
        }
      } else {
        // Обычный селектор
        elements = Array.from(parentElement.querySelectorAll(selector));
      }
      
      // Проверяем найденные элементы
      for (const el of elements) {
        const text = extractTextFromElement(el);
        if (text) {
          return text;
        }
      }
    } catch (e) {
      // Игнорируем ошибки селекторов и продолжаем
      console.debug(`Selector error for "${selector}":`, e.message);
    }
  }
  
  return null;
}

// Извлечение текста из конкретного элемента
function extractTextFromElement(element) {
  if (!element) return null;
  
  // Для input/select элементов берем value
  if (element.tagName === 'INPUT' || element.tagName === 'SELECT') {
    return element.value || null;
  }
  
  // Для элементов с одним текстовым узлом
  if (element.childNodes.length === 1 && element.childNodes[0].nodeType === Node.TEXT_NODE) {
    const text = element.textContent.trim();
    return text || null;
  }
  
  // Для сложных элементов ищем текст, исключая вложенные labels
  const clonedElement = element.cloneNode(true);
  const labels = clonedElement.querySelectorAll('label');
  labels.forEach(label => label.remove());
  
  const text = clonedElement.textContent.trim();
  return text || null;
}

// Парсинг числовых значений
function parseNumber(text) {
  if (!text) return 0;
  
  // Убираем все символы кроме цифр, точек и запятых
  const cleaned = text.replace(/[^\d\.,]/g, '');
  
  // Конвертируем в число
  const number = parseFloat(cleaned.replace(/,/g, ''));
  
  return isNaN(number) ? 0 : number;
}

// Расчет прибыльности груза
function calculateProfitability(load) {
  const totalMiles = load.miles + load.deadhead;
  const ratePerMile = totalMiles > 0 ? load.rate / totalMiles : 0;
  const deadheadRatio = load.miles > 0 ? load.deadhead / load.miles : 1;
  
  // Коэффициент прибыльности (учитывает deadhead)
  const profitabilityScore = ratePerMile * (1 - deadheadRatio * 0.3);
  
  // Определяем приоритет
  let priority = 'LOW';
  if (profitabilityScore > 3.5) {
    priority = 'HIGH';
  } else if (profitabilityScore > 2.5) {
    priority = 'MEDIUM';
  }
  
  return {
    ratePerMile,
    profitabilityScore,
    deadheadRatio,
    isProfitable: ratePerMile >= 2.50 && deadheadRatio <= 0.25,
    priority
  };
}

// Проверка фильтров
function passesFilters(load, profitability) {
  const settings = monitoringState.settings || {};
  
  // Минимальная ставка за милю
  if (profitability.ratePerMile < (settings.minRatePerMile || 2.50)) {
    return false;
  }
  
  // Максимальный deadhead
  if (load.deadhead > (settings.maxDeadhead || 50)) {
    return false;
  }
  
  // Минимальное расстояние
  if (load.miles < (settings.minDistance || 200)) {
    return false;
  }
  
  // Максимальное расстояние (если указано)
  if (settings.maxDistance && load.miles > settings.maxDistance) {
    return false;
  }
  
  // Фильтр по регионам (если указаны)
  if (settings.regions && settings.regions.length > 0) {
    const matchesRegion = settings.regions.some(region => 
      (load.pickup && load.pickup.toLowerCase().includes(region.toLowerCase())) ||
      (load.delivery && load.delivery.toLowerCase().includes(region.toLowerCase()))
    );
    if (!matchesRegion) {
      return false;
    }
  }
  
  return true;
}

// Адаптивная настройка интервала сканирования
function adjustScanInterval(result) {
  const currentInterval = monitoringState.adaptiveInterval;
  
  switch (result) {
    case 'loads_found':
      // Найдены новые грузы - ускоряем сканирование
      monitoringState.adaptiveInterval = Math.max(2000, currentInterval - 500);
      break;
      
    case 'no_new_loads':
      // Новых грузов нет - замедляем сканирование
      monitoringState.adaptiveInterval = Math.min(5000, currentInterval + 200);
      break;
      
    case 'no_loads':
      // Грузов вообще нет на странице - значительно замедляем
      monitoringState.adaptiveInterval = Math.min(10000, currentInterval + 1000);
      break;
      
    case 'error':
      // Ошибка - замедляем сканирование
      monitoringState.adaptiveInterval = Math.min(8000, currentInterval + 1000);
      break;
  }
  
  // Перезапускаем интервал с новой частотой
  if (monitoringState.scanInterval && monitoringState.adaptiveInterval !== currentInterval) {
    clearInterval(monitoringState.scanInterval);
    monitoringState.scanInterval = setInterval(() => {
      scanForLoads();
    }, monitoringState.adaptiveInterval);
    
    console.log(`Scan interval adjusted to ${monitoringState.adaptiveInterval}ms`);
  }
}

// Показ индикатора мониторинга
function showMonitoringIndicator() {
  // Убираем старый индикатор если есть
  hideMonitoringIndicator();
  
  const indicator = document.createElement('div');
  indicator.id = 'freightpower-monitor-indicator';
  indicator.innerHTML = `
    <div style="
      position: fixed;
      top: 10px;
      right: 10px;
      background: #4CAF50;
      color: white;
      padding: 8px 12px;
      border-radius: 4px;
      font-size: 12px;
      font-family: Arial, sans-serif;
      z-index: 10000;
      box-shadow: 0 2px 8px rgba(0,0,0,0.2);
      animation: pulse 2s infinite;
    ">
      🔍 Мониторинг активен
      <div style="font-size: 10px; opacity: 0.8;">
        Сканирований: <span id="scan-counter">0</span>
      </div>
    </div>
    <style>
      @keyframes pulse {
        0% { opacity: 1; }
        50% { opacity: 0.7; }
        100% { opacity: 1; }
      }
    </style>
  `;
  
  document.body.appendChild(indicator);
  
  // Обновляем счетчик сканирований
  setInterval(() => {
    const counter = document.getElementById('scan-counter');
    if (counter && monitoringState.isActive) {
      counter.textContent = monitoringState.scanCount;
    }
  }, 1000);
}

// Скрытие индикатора мониторинга
function hideMonitoringIndicator() {
  const indicator = document.getElementById('freightpower-monitor-indicator');
  if (indicator) {
    indicator.remove();
  }
}

// Воспроизведение звукового сигнала
function playAlertSound() {
  try {
    // Создаем audio элемент для воспроизведения звука
    const audio = new Audio(chrome.runtime.getURL('sounds/alert.mp3'));
    audio.volume = 0.7;
    
    audio.play().then(() => {
      console.log('🔊 Alert sound played');
    }).catch(error => {
      console.error('Error playing sound:', error);
      
      // Fallback: используем Web Audio API
      try {
        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        const oscillator = audioContext.createOscillator();
        const gainNode = audioContext.createGain();
        
        oscillator.connect(gainNode);
        gainNode.connect(audioContext.destination);
        
        oscillator.frequency.value = 800; // Частота звука
        gainNode.gain.value = 0.3; // Громкость
        
        oscillator.start();
        oscillator.stop(audioContext.currentTime + 0.2); // Длительность 200мс
        
        console.log('🔊 Fallback beep played');
      } catch (fallbackError) {
        console.error('Fallback sound also failed:', fallbackError);
      }
    });
  } catch (error) {
    console.error('Failed to create audio element:', error);
  }
}

// Наблюдение за изменениями страницы
function observePageChanges() {
  console.log('👁️ Starting DOM observer...');
  
  // Отслеживаем изменения URL (для SPA)
  let lastUrl = location.href;
  new MutationObserver(() => {
    const url = location.href;
    if (url !== lastUrl) {
      lastUrl = url;
      console.log('📍 URL changed:', url);
      
      // Проверяем, находимся ли мы на странице поиска
      if (url.includes('/search') || url.includes('/app/search')) {
        console.log('🔍 On search page, checking for results...');
        setTimeout(() => {
          if (monitoringState.isActive) {
            scanForLoads();
          }
        }, 1000);
      }
    }
  }).observe(document, {subtree: true, childList: true});
  
  // Создаем основной наблюдатель за DOM
  const observer = new MutationObserver((mutations) => {
    // Проверяем, были ли добавлены новые элементы
    let hasNewContent = false;
    
    for (const mutation of mutations) {
      if (mutation.type === 'childList' && mutation.addedNodes.length > 0) {
        // Проверяем, содержат ли новые узлы потенциальные грузы
        for (const node of mutation.addedNodes) {
          if (node.nodeType === Node.ELEMENT_NODE) {
            const text = node.textContent || '';
            // Ищем признаки грузов
            if (text.includes('Origin') || text.includes('Destination') || 
                text.includes('miles') || /\$\d+/.test(text) ||
                node.querySelector && node.querySelector('[class*="load"], [class*="freight"], [class*="card"]')) {
              hasNewContent = true;
              break;
            }
          }
        }
      }
      
      if (hasNewContent) break;
    }
    
    // Если обнаружен новый контент и мониторинг активен
    if (hasNewContent && monitoringState.isActive && !monitoringState.pendingScan) {
      console.log('🆕 New content detected, scheduling scan...');
      
      // Устанавливаем флаг, чтобы избежать множественных сканирований
      monitoringState.pendingScan = true;
      
      // Ждем немного, чтобы страница полностью обновилась
      setTimeout(() => {
        monitoringState.pendingScan = false;
        if (monitoringState.isActive) {
          scanForLoads();
        }
      }, 500);
    }
  });
  
  // Конфигурация наблюдателя
  const config = {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ['class', 'style'] // Отслеживаем изменения классов и стилей
  };
  
  // Запускаем наблюдение за всем документом
  observer.observe(document.body, config);
  
  // Также наблюдаем за конкретными контейнерами, если они есть
  const containers = [
    document.querySelector('.search-results'),
    document.querySelector('[class*="result-container"]'),
    document.querySelector('main'),
    document.querySelector('#app')
  ].filter(Boolean);
  
  containers.forEach(container => {
    console.log('👁️ Observing container:', container.className || container.tagName);
    observer.observe(container, config);
  });
  
  console.log('✅ DOM observer started');
}

// Очистка старых записей из кеша (каждые 30 минут)
setInterval(() => {
  const now = Date.now();
  const maxAge = 30 * 60 * 1000; // 30 минут
  
  for (const [loadId, loadData] of monitoringState.foundLoads.entries()) {
    if (now - loadData.foundAt > maxAge) {
      monitoringState.foundLoads.delete(loadId);
    }
  }
  
  console.log(`Cache cleaned. Remaining loads: ${monitoringState.foundLoads.size}`);
}, 30 * 60 * 1000);

// Диагностическая функция для анализа страницы
function diagnosePage() {
  console.log('🔍 Starting page diagnostics...');
  
  // Анализируем URL
  console.log('📍 Current URL:', window.location.href);
  console.log('📄 Page title:', document.title);
  
  // Проверяем основные контейнеры
  const containers = {
    'main': document.querySelector('main'),
    '#app': document.querySelector('#app'),
    '.search-results': document.querySelector('.search-results'),
    '[role="main"]': document.querySelector('[role="main"]'),
    '.content': document.querySelector('.content')
  };
  
  console.log('📦 Main containers found:');
  Object.entries(containers).forEach(([selector, element]) => {
    if (element) {
      console.log(`  ✅ ${selector} - ${element.className || element.id || element.tagName}`);
    }
  });
  
  // Ищем все элементы, которые могут быть карточками
  const potentialCards = [];
  
  // Поиск по классам
  const classPatterns = ['card', 'load', 'freight', 'result', 'item', 'row'];
  classPatterns.forEach(pattern => {
    const elements = document.querySelectorAll(`[class*="${pattern}"]`);
    if (elements.length > 0) {
      console.log(`🎯 Found ${elements.length} elements with class containing "${pattern}"`);
      elements.forEach(el => {
        if (el.textContent.length > 50 && el.childElementCount > 2) {
          potentialCards.push({
            element: el,
            selector: `[class*="${pattern}"]`,
            className: el.className
          });
        }
      });
    }
  });
  
  // Анализируем найденные потенциальные карточки
  console.log(`\n🃏 Found ${potentialCards.length} potential card elements:`);
  potentialCards.slice(0, 3).forEach((card, index) => {
    console.log(`\n📋 Card #${index + 1}:`);
    console.log(`  Selector: ${card.selector}`);
    console.log(`  Class: ${card.className}`);
    console.log(`  Children: ${card.element.childElementCount}`);
    console.log(`  Text preview: ${card.element.textContent.substring(0, 100).replace(/\s+/g, ' ')}...`);
    
    // Анализируем структуру
    const structure = analyzeElementStructure(card.element);
    console.log(`  Structure:`, structure);
  });
  
  // Проверяем наличие ключевых слов на странице
  const keywords = ['Origin', 'Destination', 'Capacity Type', 'miles', 'Romeoville', 'Dayville'];
  console.log('\n🔤 Keyword search:');
  keywords.forEach(keyword => {
    const count = (document.body.textContent.match(new RegExp(keyword, 'gi')) || []).length;
    if (count > 0) {
      console.log(`  ✅ "${keyword}" found ${count} times`);
    }
  });
  
  return potentialCards;
}

// Анализ структуры элемента
function analyzeElementStructure(element) {
  const structure = {
    tag: element.tagName,
    classes: element.className.split(' ').filter(c => c),
    hasOrigin: false,
    hasDestination: false,
    hasDate: false,
    hasMiles: false,
    hasPrice: false,
    textFields: []
  };
  
  // Рекурсивный поиск текстовых полей
  function findTextFields(el, depth = 0) {
    if (depth > 3) return; // Ограничиваем глубину
    
    for (const child of el.children) {
      const text = child.textContent.trim();
      
      if (text && child.children.length === 0) {
        structure.textFields.push({
          text: text.substring(0, 50),
          tag: child.tagName,
          class: child.className
        });
        
        // Проверяем содержимое
        if (text.includes('Origin')) structure.hasOrigin = true;
        if (text.includes('Destination')) structure.hasDestination = true;
        if (/\b\d{1,2}\/\d{1,2}\/\d{2,4}\b/.test(text) || /\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b/i.test(text)) structure.hasDate = true;
        if (/\b\d+\s*mi/i.test(text)) structure.hasMiles = true;
        if (/\$\d+/.test(text)) structure.hasPrice = true;
      }
      
      findTextFields(child, depth + 1);
    }
  }
  
  findTextFields(element);
  
  return structure;
}

// Добавляем команду для запуска диагностики через консоль
window.freightDiag = diagnosePage;
console.log('💡 Tip: Run "freightDiag()" in console to diagnose page structure');

console.log('FreightPower Load Monitor content script initialized');
