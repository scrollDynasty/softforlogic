// FreightPower Load Monitor - Content Script

// Селекторы для парсинга (с fallback'ами)
const SELECTORS = {
  load_items: [
    '[data-testid="load-row"]',
    '.load-item, .freight-item',
    'tr[class*="load"], tbody tr',
    '.search-results tr',
    '[class*="row"][class*="load"]',
    'table tbody tr'
  ],
  load_id: [
    '[data-testid="reference"]',
    '.load-reference, .id-column',
    'td:first-child',
    '[class*="id"]',
    '[class*="reference"]'
  ],
  pickup_location: [
    '[data-testid="pickup-location"]',
    '.origin, .pickup, .pickup-location',
    'td:nth-child(2)',
    '[class*="origin"]',
    '[class*="pickup"]'
  ],
  delivery_location: [
    '[data-testid="delivery-location"]',
    '.destination, .delivery, .delivery-location',
    'td:nth-child(3)',
    '[class*="destination"]',
    '[class*="delivery"]'
  ],
  miles: [
    '[data-testid="miles"]',
    '.distance, .total-miles, .miles-column',
    'td:nth-child(4)',
    '[class*="miles"]',
    '[class*="distance"]'
  ],
  deadhead: [
    '[data-testid="deadhead"]',
    '.deadhead, .empty-miles',
    'td:nth-child(5)',
    '[class*="deadhead"]',
    '[class*="empty"]'
  ],
  rate: [
    '[data-testid="rate"]',
    '.rate, .price, .pay, .freight-rate',
    'td:nth-child(6)',
    '[class*="rate"]',
    '[class*="price"]',
    '[class*="pay"]'
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
  adaptiveInterval: 3000
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

// Детекция успешной авторизации
function detectLogin() {
  const loginIndicators = [
    // Проверяем URL
    !window.location.href.includes('/login') && !window.location.href.includes('/signin'),
    
    // Проверяем наличие элементов авторизованного пользователя
    document.querySelector('[data-user-authenticated]'),
    document.querySelector('.dashboard'),
    document.querySelector('.user-menu'),
    document.querySelector('.header-user'),
    document.querySelector('[class*="user-nav"]'),
    document.querySelector('[class*="profile"]'),
    document.querySelector('nav[class*="user"]'),
    
    // Проверяем localStorage/sessionStorage
    localStorage.getItem('userToken'),
    localStorage.getItem('authToken'),
    sessionStorage.getItem('userToken'),
    sessionStorage.getItem('authToken'),
    
    // Проверяем cookies
    document.cookie.includes('auth'),
    document.cookie.includes('session'),
    document.cookie.includes('token'),
    
    // Проверяем наличие основного контента (не страница логина)
    document.querySelector('.loads-table'),
    document.querySelector('[class*="freight"]'),
    document.querySelector('.search-results'),
    
    // Проверяем отсутствие форм логина
    !document.querySelector('form[class*="login"]'),
    !document.querySelector('input[type="password"]')
  ];
  
  // Если большинство индикаторов положительные, считаем что авторизованы
  const positiveCount = loginIndicators.filter(Boolean).length;
  return positiveCount >= 3;
}

// Проверка статуса авторизации
function checkLoginStatus() {
  const wasLoggedIn = monitoringState.isLoggedIn;
  const isLoggedIn = detectLogin();
  
  if (isLoggedIn !== wasLoggedIn) {
    monitoringState.isLoggedIn = isLoggedIn;
    
    if (isLoggedIn) {
      console.log('Login detected, notifying background script');
      chrome.runtime.sendMessage({
        type: 'LOGIN_DETECTED',
        url: window.location.href
      });
    } else {
      console.log('Logout detected, stopping monitoring');
      stopMonitoring();
      chrome.runtime.sendMessage({
        type: 'LOGOUT_DETECTED'
      });
    }
  }
}

// Обработка сообщений от background script
function handleMessage(message, sender, sendResponse) {
  switch (message.type) {
    case 'START_MONITORING':
      startMonitoring(message.settings);
      sendResponse({ success: true });
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
      
    case 'UPDATE_SETTINGS':
      monitoringState.settings = message.settings;
      if (monitoringState.isActive) {
        restartMonitoring();
      }
      sendResponse({ success: true });
      break;
      
    case 'PLAY_SOUND':
      playAlertSound();
      sendResponse({ success: true });
      break;
      
    default:
      console.log('Unknown message type:', message.type);
  }
  
  return true;
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
  for (const selector of SELECTORS.load_items) {
    const elements = document.querySelectorAll(selector);
    if (elements.length > 0) {
      console.log(`Found ${elements.length} load elements using selector: ${selector}`);
      return Array.from(elements);
    }
  }
  return [];
}

// Парсинг данных груза из элемента
function parseLoadElement(element) {
  const loadData = {
    id: null,
    pickup: null,
    delivery: null,
    miles: 0,
    deadhead: 0,
    rate: 0,
    element: element
  };
  
  // Извлекаем ID груза
  loadData.id = extractText(element, SELECTORS.load_id);
  
  // Извлекаем место погрузки
  loadData.pickup = extractText(element, SELECTORS.pickup_location);
  
  // Извлекаем место разгрузки
  loadData.delivery = extractText(element, SELECTORS.delivery_location);
  
  // Извлекаем мили
  const milesText = extractText(element, SELECTORS.miles);
  loadData.miles = parseNumber(milesText);
  
  // Извлекаем deadhead
  const deadheadText = extractText(element, SELECTORS.deadhead);
  loadData.deadhead = parseNumber(deadheadText);
  
  // Извлекаем ставку
  const rateText = extractText(element, SELECTORS.rate);
  loadData.rate = parseNumber(rateText);
  
  // Валидация данных
  if (!loadData.id || loadData.miles <= 0 || loadData.rate <= 0) {
    console.warn('Invalid load data:', loadData);
    return null;
  }
  
  return loadData;
}

// Извлечение текста из элемента по селекторам
function extractText(parentElement, selectors) {
  for (const selector of selectors) {
    const element = parentElement.querySelector(selector);
    if (element && element.textContent.trim()) {
      return element.textContent.trim();
    }
  }
  
  // Fallback: ищем в самом родительском элементе
  const cells = parentElement.querySelectorAll('td, div, span');
  for (const cell of cells) {
    const text = cell.textContent.trim();
    if (text && text.length > 0) {
      // Пытаемся определить тип данных по содержимому
      if (selectors === SELECTORS.load_id && /^[A-Z0-9-]{5,}/.test(text)) {
        return text;
      }
      if (selectors === SELECTORS.miles && /\d+/.test(text)) {
        return text;
      }
      if (selectors === SELECTORS.rate && /[\$\d\.,]+/.test(text)) {
        return text;
      }
    }
  }
  
  return null;
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
    // Создаем простой звуковой сигнал
    const audioContext = new (window.AudioContext || window.webkitAudioContext)();
    const oscillator = audioContext.createOscillator();
    const gainNode = audioContext.createGain();
    
    oscillator.connect(gainNode);
    gainNode.connect(audioContext.destination);
    
    oscillator.frequency.value = 800; // Частота звука
    oscillator.type = 'sine';
    
    gainNode.gain.setValueAtTime(0, audioContext.currentTime);
    gainNode.gain.linearRampToValueAtTime(0.3, audioContext.currentTime + 0.01);
    gainNode.gain.linearRampToValueAtTime(0, audioContext.currentTime + 0.3);
    
    oscillator.start(audioContext.currentTime);
    oscillator.stop(audioContext.currentTime + 0.3);
    
    console.log('Alert sound played');
  } catch (error) {
    console.error('Error playing sound:', error);
  }
}

// Наблюдение за изменениями страницы
function observePageChanges() {
  const observer = new MutationObserver((mutations) => {
    let shouldRescan = false;
    
    mutations.forEach((mutation) => {
      // Проверяем добавление новых элементов
      if (mutation.type === 'childList' && mutation.addedNodes.length > 0) {
        for (const node of mutation.addedNodes) {
          if (node.nodeType === Node.ELEMENT_NODE) {
            // Проверяем, добавились ли элементы грузов
            for (const selector of SELECTORS.load_items) {
              if (node.matches && node.matches(selector)) {
                shouldRescan = true;
                break;
              }
              if (node.querySelector && node.querySelector(selector)) {
                shouldRescan = true;
                break;
              }
            }
          }
        }
      }
    });
    
    // Запускаем дополнительное сканирование при изменении страницы
    if (shouldRescan && monitoringState.isActive) {
      console.log('Page content changed, triggering additional scan...');
      setTimeout(() => scanForLoads(), 1000);
    }
  });
  
  // Начинаем наблюдение за изменениями DOM
  observer.observe(document.body, {
    childList: true,
    subtree: true,
    attributes: false,
    characterData: false
  });
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

console.log('FreightPower Load Monitor content script initialized');
