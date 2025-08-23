// FreightPower Load Monitor - Content Script

// Селекторы для парсинга (обновленные для FreightPower и LOTHIAN)
const SELECTORS = {
  load_items: [
    'ion-card.card-content-load-web'
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
    '[class*="reference"]',
    // LOTHIAN: ID обычно в первой колонке
    'td:nth-child(1)',
    'div:nth-child(1)',
    '[class*="col"]:first-child'
  ],
  capacity_type: [
    '[class*="capacity-type"]',
    '[class*="equipment-type"]',
    '[class*="type"]'
  ],
  pickup_location: [
    '.origin_city',
    '[class*="origin"]',
    '[class*="pickup"]',
    '[data-testid="pickup-location"]',
    '.origin, .pickup, .pickup-location',
    'td:nth-child(2)',
    // LOTHIAN: Локации обычно в определенных колонках
    'td:nth-child(3)',
    'td:nth-child(4)',
    '[class*="col"]:nth-child(3)',
    '[class*="col"]:nth-child(4)'
  ],
  delivery_location: [
    '.origin_city:nth-of-type(2)',
    '[class*="destination"]',
    '[class*="delivery"]',
    '[data-testid="delivery-location"]',
    '.destination, .delivery, .delivery-location',
    'td:nth-child(3)',
    // LOTHIAN: Destination обычно после pickup
    'td:nth-child(4)',
    'td:nth-child(5)',
    '[class*="col"]:nth-child(4)',
    '[class*="col"]:nth-child(5)'
  ],
  pickup_date: [
    '[class*="pickup-date"]',
    '[class*="origin-date"]',
    '[class*="start-date"]'
  ],
  delivery_date: [
    '[class*="delivery-date"]',
    '[class*="destination-date"]',
    '[class*="end-date"]'
  ],
  miles: [
    '.card-distance[data-testid="card-distance"]',
    '[data-testid="card-distance"]',
    '.card-distance',
    '[class*="miles"]',
    '[class*="distance"]',
    '[data-testid="miles"]',
    '.distance, .total-miles, .miles-column',
    'td:nth-child(4)',
    // LOTHIAN: Мили в различных позициях
    'td:nth-child(2)',
    'td:nth-child(3)',
    '[class*="col"]:nth-child(2)',
    '[class*="col"]:nth-child(3)'
  ],
  deadhead: [
    '.origin_dateTime.load_header_elements.stop-appointment',
    '[class*="deadhead"]',
    '[class*="empty-miles"]',
    '[data-testid="deadhead"]',
    '.deadhead, .empty-miles',
    'td:nth-child(5)'
  ],
  rate: [
    '.rate-amount',
    '[class*="rate"]',
    '[class*="price"]',
    '[class*="pay"]',
    '[data-testid="rate"]',
    '.rate, .price, .pay, .freight-rate',
    'td:nth-child(6)',
    // LOTHIAN: Ставка обычно в колонках
    'td:nth-child(2)',
    'td:nth-child(3)',
    '[class*="col"]:nth-child(2)',
    '[class*="col"]:nth-child(3)',
    // Ionic специфичные селекторы для цены
    'p.card-price',
    '.card-price',
    'ion-label[class*="price"]',
    'ion-text[class*="price"]'
  ],
  radius: [
    '[class*="radius"]',
    'select[class*="radius"]',
    'input[type="range"]'
  ]
};

// Состояние мониторинга
let monitoringState = {
  isActive: false,
  isLoggedIn: false,
  scanInterval: null,
  settings: {
    minRatePerMile: 2.5,
    maxDeadhead: 50,
    scanInterval: 3000,
    soundAlerts: true
  }, // Настройки по умолчанию
  foundLoads: new Map(), // Кеш найденных грузов для избежания дубликатов
  lastScanTime: 0,
  scanCount: 0,
  adaptiveInterval: 3000,
  pendingScan: false, // Флаг для отслеживания ожидающих сканирований
  scanTimeout: null, // Таймаут для сканирования
  watchdogInterval: null // Интервал для watchdog
};

// Инициализация при загрузке
(function initialize() {
  console.log('🚀 FreightPower Load Monitor content script загружен');

// Функция для получения корневого элемента карточки
function getCardRoot(el) {
  if (!el) return null;
  return el.matches && el.matches('ion-card.card-content-load-web')
    ? el
    : el.closest && el.closest('ion-card.card-content-load-web');
}

// Функция для проверки минимальных данных
function hasMinimalData(load) {
  if (!load) return false;
  return (
    (load.pickup && load.pickup !== 'Неизвестно') ||
    (load.delivery && load.delivery !== 'Неизвестно') ||
    (load.rate && load.rate > 0) ||
    (load.miles && load.miles > 0)
  );
}
  
  // Определяем и логируем тип сайта
  const siteType = detectSiteType();
  console.log(`🌐 Определен тип сайта: ${siteType} (URL: ${window.location.href})`);
  
  // Проверяем авторизацию при загрузке
  checkLoginStatus();
  
  // Слушаем сообщения от background script
  chrome.runtime.onMessage.addListener(handleMessage);
  
  // Периодически проверяем авторизацию и автоматически запускаем мониторинг
  setInterval(() => {
    checkLoginStatus();
    
    // Автоматический запуск мониторинга если пользователь авторизован
    if (monitoringState.isLoggedIn && !monitoringState.isActive) {
      console.log('🔄 Пользователь авторизован, автоматически запускаем мониторинг...');
      startAutomaticMonitoring();
    }
  }, 5000);
  
  // Наблюдаем за изменениями DOM
  observePageChanges();
  
  // Дополнительные слушатели для отслеживания навигации
  window.addEventListener('popstate', () => {
    setTimeout(() => checkLoginStatus(true), 1000);
  });
  
  // Слушаем изменения в истории (для SPA)
  const originalPushState = history.pushState;
  const originalReplaceState = history.replaceState;
  
  history.pushState = function() {
    originalPushState.apply(history, arguments);
    setTimeout(() => checkLoginStatus(true), 1000);
  };
  
  history.replaceState = function() {
    originalReplaceState.apply(history, arguments);
    setTimeout(() => checkLoginStatus(true), 1000);
  };
  
  // Попытка автоматического запуска через 3 секунды после загрузки
  setTimeout(() => {
    if (monitoringState.isLoggedIn && !monitoringState.isActive) {
      console.log('⚡ Автоматический запуск мониторинга при загрузке...');
      startAutomaticMonitoring();
    }
  }, 3000);
  
  // Глобальные функции для отладки авторизации
  window.freightAuthCheck = function() {
    console.log('🔍 Ручная проверка авторизации:');
    const result = detectLogin();
    console.log('Результат:', result ? '✅ Авторизован' : '❌ Не авторизован');
    return result;
  };
  
  window.freightForceReauth = function() {
    console.log('🔄 Принудительная перепроверка авторизации...');
    forceReCheckAuth();
  };
})();

// Детекция успешной авторизации (улучшенная версия)
function detectLogin() {
  // Проверяем URL
  const isOnFreightPower = window.location.href.includes('freightpower.schneider.com');
  const currentUrl = window.location.href.toLowerCase();
  
  // Более точное определение страниц входа
  const loginPagePatterns = ['/login', '/signin', '/auth', '/authenticate', '/sign-in'];
  const isOnLoginPage = loginPagePatterns.some(pattern => currentUrl.includes(pattern));
  
  if (!isOnFreightPower) {
    return false;
  }
  
  // Если на странице логина - точно не авторизован
  if (isOnLoginPage) {
    return false;
  }
  
  // Проверяем заголовок страницы на наличие признаков входа
  const titleIndicatesLogin = document.title.toLowerCase().includes('login') ||
                             document.title.toLowerCase().includes('sign in') ||
                             document.title.toLowerCase().includes('authenticate') ||
                             document.title.toLowerCase().includes('access denied');
  
  if (titleIndicatesLogin) {
    return false;
  }
  
  // ПРИОРИТЕТНАЯ ПРОВЕРКА: Storage и cookies (самый надежный способ)
  const authStorageKeys = [
    'userToken', 'authToken', 'auth', 'accessToken', 'jwt',
    'session', 'user', 'userData', 'schneider_auth', 
    'freightpower_auth', 'auth_token', 'bearer_token',
    'access_token', 'refresh_token', 'authorization'
  ];
  
  const hasAuthStorage = authStorageKeys.some(key => {
    const localValue = localStorage.getItem(key);
    const sessionValue = sessionStorage.getItem(key);
    return (localValue && localValue !== 'null' && localValue !== 'undefined') ||
           (sessionValue && sessionValue !== 'null' && sessionValue !== 'undefined');
  });
  
  // Более точная проверка cookies
  const authCookiePatterns = [
    'auth', 'session', 'token', 'jwt', 'bearer',
    'schneider', 'freightpower', 'user', 'access'
  ];
  
  const hasAuthCookie = authCookiePatterns.some(pattern => {
    const cookies = document.cookie.toLowerCase();
    // Проверяем что cookie не только существует, но и имеет значение
    const regex = new RegExp(`${pattern}[^=]*=([^;]+)`);
    const match = cookies.match(regex);
    return match && match[1] && match[1].trim() !== '' && match[1] !== 'null';
  });
  
  // Если есть токены/куки авторизации - считаем авторизованным
  if (hasAuthStorage || hasAuthCookie) {
    console.log('🔑 Найдены токены авторизации:', { hasAuthStorage, hasAuthCookie });
    return true;
  }
  
  // ВТОРИЧНАЯ ПРОВЕРКА: Элементы интерфейса авторизованного пользователя
  const strongAuthIndicators = [
    // Сильные индикаторы (специфичные для авторизованных пользователей)
    document.querySelector('[data-user-authenticated="true"]'),
    document.querySelector('[data-user-id]'),
    document.querySelector('.user-avatar'),
    document.querySelector('.profile-dropdown'),
    document.querySelector('[class*="user-profile"]'),
    document.querySelector('[class*="account-menu"]'),
    document.querySelector('.logout'),
    document.querySelector('[href*="logout"]'),
    document.querySelector('[onclick*="logout"]'),
    document.querySelector('.user-menu'),
    document.querySelector('.header-user')
  ];
  
  const hasStrongAuthElement = strongAuthIndicators.some(el => el !== null);
  
  if (hasStrongAuthElement) {
    console.log('👤 Найдены элементы авторизованного пользователя');
    return true;
  }
  
  // ТРЕТИЧНАЯ ПРОВЕРКА: Проверяем отсутствие форм входа
  const loginFormElements = [
    document.querySelector('input[name="password"]'),
    document.querySelector('input[type="password"]'),
    document.querySelector('.login-form'),
    document.querySelector('form[action*="login"]'),
    document.querySelector('form[action*="signin"]'),
    document.querySelector('[class*="signin-form"]'),
    document.querySelector('[class*="login-container"]')
  ];
  
  const hasLoginForm = loginFormElements.some(el => el !== null);
  
  // Проверяем наличие основных элементов приложения
  const appIndicators = [
    document.querySelector('.search-results'),
    document.querySelector('[class*="search-container"]'),
    document.querySelector('[class*="load-list"]'),
    document.querySelector('[class*="freight-list"]'),
    document.querySelector('main[class*="app"]'),
    document.querySelector('[role="main"]'),
    document.querySelector('#app[class*="authenticated"]'),
    document.querySelector('.content[class*="main"]')
  ];
  
  const hasAppElements = appIndicators.some(el => el !== null);
  
  // Финальная логика: если есть элементы приложения и НЕТ форм входа
  const isLoggedIn = hasAppElements && !hasLoginForm && !titleIndicatesLogin;
  
  // Детальное логирование для отладки
  console.log('🔍 Расширенная проверка авторизации:', {
    url: window.location.href,
    title: document.title,
    isOnFreightPower,
    isOnLoginPage,
    titleIndicatesLogin,
    hasAuthStorage,
    hasAuthCookie,
    hasStrongAuthElement,
    hasLoginForm,
    hasAppElements,
    finalResult: isLoggedIn
  });
  
  return isLoggedIn;
}

// Проверка статуса авторизации
function checkLoginStatus(force = false) {
  const wasLoggedIn = monitoringState.isLoggedIn;
  const newLoginStatus = detectLogin();
  
  // Обновляем статус
  monitoringState.isLoggedIn = newLoginStatus;
  
  // Логируем для отладки
  if (force) {
    console.log('🔄 Принудительная проверка авторизации:', {
      previous: wasLoggedIn,
      current: newLoginStatus,
      changed: wasLoggedIn !== newLoginStatus
    });
  }
  
  // Если статус изменился
  if (wasLoggedIn !== monitoringState.isLoggedIn) {
    if (monitoringState.isLoggedIn) {
      console.log('✅ User logged in to FreightPower');
      safeSendMessage({ 
        type: 'LOGIN_DETECTED',
        url: window.location.href
      }).catch(error => {
        console.error('Error sending login message:', error);
      });
    } else {
      console.log('🔒 User logged out from FreightPower');
      safeSendMessage({ type: 'LOGOUT_DETECTED' }).catch(error => {
        console.error('Error sending logout message:', error);
      });
      stopMonitoring();
    }
  }
}

// Функция для принудительной повторной проверки авторизации
function forceReCheckAuth() {
  console.log('🔄 Принудительная перепроверка авторизации...');
  checkLoginStatus(true);
  
  // Дополнительная задержка для асинхронной загрузки элементов
  setTimeout(() => {
    console.log('🔄 Повторная проверка через 2 сек...');
    checkLoginStatus(true);
  }, 2000);
  
  setTimeout(() => {
    console.log('🔄 Финальная проверка через 5 сек...');
    checkLoginStatus(true);
  }, 5000);
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
      
    case 'FORCE_RECHECK_AUTH':
      forceReCheckAuth();
      sendResponse({ 
        success: true, 
        currentStatus: monitoringState.isLoggedIn 
      });
      break;
      
    case 'FORCE_SCAN':
      if (monitoringState.isActive) {
        scanForLoads();
        sendResponse({ success: true });
      } else {
        sendResponse({ success: false, reason: 'Monitoring not active' });
      }
      break;
      
    case 'UPDATE_SETTINGS':
      if (message.settings) {
        console.log('Updating monitoring settings:', message.settings);
        
        // Убеждаемся что у нас есть базовые настройки
        if (!monitoringState.settings) {
          monitoringState.settings = {
            minRatePerMile: 2.5,
            maxDeadhead: 50,
            scanInterval: 3000,
            soundAlerts: true
          };
        }
        
        // Объединяем с существующими настройками
        monitoringState.settings = {
          ...monitoringState.settings,
          ...message.settings
        };
        
        // Обновляем адаптивный интервал если он изменился
        if (message.settings.scanInterval && message.settings.scanInterval !== monitoringState.adaptiveInterval) {
          monitoringState.adaptiveInterval = message.settings.scanInterval;
        }
        
        // Если мониторинг активен, перезапускаем с новыми настройками
        if (monitoringState.isActive) {
          restartMonitoring(message.settings);
        }
        
        sendResponse({ success: true });
      } else {
        sendResponse({ success: false, reason: 'No settings provided' });
      }
      break;
      
    default:
      console.warn('Unknown message type:', message.type);
      sendResponse({ success: false, reason: 'Unknown message type' });
  }
  
  return true; // Указывает, что ответ может быть асинхронным
}

// Запуск мониторинга (улучшенная версия)
function startMonitoring(settings) {
  if (monitoringState.isActive) {
    console.log('Monitoring already active');
    return;
  }
  
  if (!monitoringState.isLoggedIn) {
    console.log('Cannot start monitoring: not logged in');
    return;
  }
  
  // Убеждаемся что у нас есть базовые настройки
  if (!monitoringState.settings) {
    monitoringState.settings = {
      minRatePerMile: 2.5,
      maxDeadhead: 50,
      scanInterval: 3000,
      soundAlerts: true
    };
  }
  
  // Объединяем переданные настройки с существующими
  if (settings) {
    monitoringState.settings = {
      ...monitoringState.settings,
      ...settings
    };
  }
  
  monitoringState.isActive = true;
  monitoringState.scanCount = 0;
  monitoringState.foundLoads.clear();
  monitoringState.lastScanTime = Date.now();
  monitoringState.pendingScan = false;
  
  console.log('Starting automatic load monitoring with settings:', monitoringState.settings);
  
  // Запускаем первое сканирование сразу
  scheduleNextScan(0);
  
  // Показываем индикатор активности
  showMonitoringIndicator();
  
  // Устанавливаем watchdog для автоматического восстановления
  startMonitoringWatchdog();
}

// Остановка мониторинга (улучшенная версия)
function stopMonitoring() {
  if (!monitoringState.isActive) {
    return;
  }
  
  monitoringState.isActive = false;
  monitoringState.pendingScan = false;
  
  if (monitoringState.scanInterval) {
    clearInterval(monitoringState.scanInterval);
    monitoringState.scanInterval = null;
  }
  
  if (monitoringState.scanTimeout) {
    clearTimeout(monitoringState.scanTimeout);
    monitoringState.scanTimeout = null;
  }
  
  if (monitoringState.watchdogInterval) {
    clearInterval(monitoringState.watchdogInterval);
    monitoringState.watchdogInterval = null;
  }
  
  hideMonitoringIndicator();
  
  console.log('Load monitoring stopped');
}

// Планирование следующего сканирования
function scheduleNextScan(delay) {
  if (!monitoringState.isActive) return;
  
  if (monitoringState.scanTimeout) {
    clearTimeout(monitoringState.scanTimeout);
  }
  
  const actualDelay = delay || monitoringState.adaptiveInterval;
  
  monitoringState.scanTimeout = setTimeout(() => {
    if (monitoringState.isActive && monitoringState.isLoggedIn && !monitoringState.pendingScan) {
      performScan();
    }
  }, actualDelay);
}

// Выполнение сканирования с защитой от зависания
function performScan() {
  if (!monitoringState.isActive || !monitoringState.isLoggedIn || monitoringState.pendingScan) {
    return;
  }
  
  monitoringState.pendingScan = true;
  monitoringState.lastScanTime = Date.now();
  
  // Устанавливаем таймаут для предотвращения зависания
  const scanTimeout = setTimeout(() => {
    if (monitoringState.pendingScan) {
      console.warn('Scan timeout, resetting pending state');
      monitoringState.pendingScan = false;
      scheduleNextScan();
    }
  }, 30000); // 30 секунд максимум на сканирование
  
  try {
    scanForLoads();
  } catch (error) {
    console.error('Error during scan:', error);
  } finally {
    clearTimeout(scanTimeout);
    monitoringState.pendingScan = false;
    
    // Планируем следующее сканирование
    if (monitoringState.isActive) {
      scheduleNextScan();
    }
  }
}

// Watchdog для мониторинга состояния
function startMonitoringWatchdog() {
  if (monitoringState.watchdogInterval) {
    clearInterval(monitoringState.watchdogInterval);
  }
  
  monitoringState.watchdogInterval = setInterval(() => {
    if (!monitoringState.isActive) return;
    
    const now = Date.now();
    const timeSinceLastScan = now - monitoringState.lastScanTime;
    const maxIdleTime = monitoringState.adaptiveInterval * 3; // 3 интервала максимум
    
    // Проверяем, не зависло ли сканирование
    if (timeSinceLastScan > maxIdleTime) {
      console.warn('Monitoring appears to be stuck, restarting...');
      restartMonitoring();
      return;
    }
    
    // Проверяем, что пользователь еще авторизован
    if (!monitoringState.isLoggedIn) {
      console.log('User is no longer logged in, stopping monitoring');
      stopMonitoring();
      return;
    }
    
    // Проверяем доступность страницы
    if (document.hidden || !document.hasFocus()) {
      console.log('Page is hidden or not focused, reducing scan frequency');
      monitoringState.adaptiveInterval = Math.min(monitoringState.adaptiveInterval * 1.5, 15000);
    } else {
      // Восстанавливаем нормальную частоту если страница активна
      const normalInterval = (monitoringState.settings && monitoringState.settings.scanInterval) || 3000;
      if (monitoringState.adaptiveInterval > normalInterval) {
        monitoringState.adaptiveInterval = Math.max(monitoringState.adaptiveInterval * 0.8, normalInterval);
      }
    }
    
  }, 15000); // Проверяем каждые 15 секунд
}

// Перезапуск мониторинга с новыми настройками (улучшенная версия)
function restartMonitoring(newSettings) {
  if (monitoringState.isActive) {
    const settings = newSettings || monitoringState.settings;
    console.log('Restarting monitoring with settings:', settings);
    
    stopMonitoring();
    
    // Небольшая задержка перед перезапуском
    setTimeout(() => {
      if (monitoringState.isLoggedIn) {
        startMonitoring(settings);
      }
    }, 2000);
  }
}

// Основная функция сканирования грузов (оптимизированная версия)
function scanForLoads() {
  if (!monitoringState.isActive || !monitoringState.isLoggedIn) {
    return;
  }
  
  const startTime = Date.now();
  monitoringState.scanCount++;
  
  console.log(`🔍 Автоматическое сканирование грузов... (сканирование №${monitoringState.scanCount})`);
  
  try {
    // Очищаем старые записи из кеша для предотвращения утечек памяти
    cleanupFoundLoadsCache();
    
    // Сначала проверяем что мы находимся на правильной странице
    if (!isOnLoadSearchPage()) {
      console.log('📍 Не на странице поиска грузов, перенаправляем...');
      navigateToLoadSearchPage();
      return;
    }
    
    // Логирование типа сайта один раз при старте скана
    const siteType = detectSiteType();
    console.log('Site type:', siteType);
    
    // Получаем сырые элементы и нормализуем их
    const rawNodes = Array.from(document.querySelectorAll(SELECTORS.load_items[0]));
    // На случай если остались другие селекторы — нормализуем:
    const normalized = rawNodes
      .map(getCardRoot)
      .filter(Boolean);

    // Уникализируем по самому элементу
    const loadElements = Array.from(new Set(normalized));
    
    if (loadElements.length === 0) {
      console.log('❌ Грузы не найдены на странице, пробуем обновить поиск...');
      attemptRefreshSearch();
      adjustScanInterval('no_loads');
      return;
    }
    
    console.log(`Found ${loadElements.length} load elements`);
    
    let newLoadsFound = 0;
    let profitableLoadsFound = 0;
    const batchSize = 10; // Обрабатываем по 10 элементов за раз
    
    // Обрабатываем элементы батчами для лучшей производительности
    for (let i = 0; i < loadElements.length; i += batchSize) {
      const batch = loadElements.slice(i, i + batchSize);
      
      batch.forEach((element, batchIndex) => {
        try {
          console.log(`🔍 Парсинг элемента ${i + batchIndex + 1}/${loadElements.length}`);
          const load = parseLoadElement(element);
          
          if (!loadData) {
            console.warn(`⚠️ Элемент ${i + batchIndex + 1} вернул null данные`);
            return;
          }
          
          // Проверяем минимальную осмысленность данных (базовая проверка перед ID)
          const hasBasicData = (
            (loadData.pickup && loadData.pickup !== 'Неизвестно') ||
            (loadData.delivery && loadData.delivery !== 'Неизвестно') ||
            (loadData.rate && loadData.rate > 0) ||
            (loadData.miles && loadData.miles > 0)
          );
          
          if (!hasBasicData) {
            // Молча пропускаем элементы без осмысленных данных
            return;
          }
          
          if (!load.id) {
            // Логируем только если есть достаточно данных для груза
            if (load.pickup && load.delivery && 
                load.pickup !== 'Неизвестно' && load.delivery !== 'Неизвестно') {
              console.log(`🔧 Элемент ${i + batchIndex + 1} без исходного ID, будет сгенерирован автоматически`);
            } else if (hasBasicData) {
              console.warn(`⚠️ Элемент ${i + batchIndex + 1} без ID но с частичными данными:`, {
                pickup: load.pickup,
                delivery: load.delivery,
                rate: load.rate,
                miles: load.miles
              });
            }
          }
          
          if (load && load.id && !monitoringState.foundLoads.has(load.id)) {
            // Новый груз найден
            monitoringState.foundLoads.set(load.id, {
              ...load,
              foundAt: Date.now(),
              scanNumber: monitoringState.scanCount
            });
            
            newLoadsFound++;
            
            // Рассчитываем прибыльность
            const profitability = calculateProfitability(load);
            
            if (profitability.isProfitable && passesFilters(load, profitability)) {
              profitableLoadsFound++;
              
              const enrichedLoadData = {
                ...load,
                ...profitability,
                priority: calculatePriority(load, profitability),
                foundAt: Date.now()
              };
              
              // Отправляем в background script асинхронно
              safeSendMessage({
                type: 'LOAD_FOUND',
                data: enrichedLoadData
              }).catch(error => {
                console.error('Error sending load data:', error);
              });
              
              console.log('💰 Profitable load found:', enrichedLoadData);
            }
          }
          
        } catch (parseError) {
          console.error(`Error parsing load element ${i + batchIndex}:`, {
            error: parseError.message || parseError,
            stack: parseError.stack,
            element: element ? {
              tagName: element.tagName,
              className: element.className,
              id: element.id,
              textContent: element.textContent?.substring(0, 100) + '...'
            } : 'element is null'
          });
        }
      });
      
      // Небольшая пауза между батчами для предотвращения блокировки UI
      if (i + batchSize < loadElements.length) {
        // Используем Promise для асинхронной обработки
        setTimeout(() => {}, 0);
      }
    }
    
    const endTime = Date.now();
    const scanDuration = endTime - startTime;
    
    console.log(`Scan completed: ${newLoadsFound} new loads, ${profitableLoadsFound} profitable (${scanDuration}ms)`);
    
    // Адаптируем интервал на основе результатов
    if (profitableLoadsFound > 0) {
      adjustScanInterval('profitable_found');
    } else if (newLoadsFound > 0) {
      adjustScanInterval('loads_found');
    } else {
      adjustScanInterval('no_new_loads');
    }
    
    // Предупреждение о медленном сканировании
    if (scanDuration > 5000) {
      console.warn(`Slow scan detected: ${scanDuration}ms`);
      adjustScanInterval('slow_scan');
    }
    
    // Обновляем статистику асинхронно с безопасной отправкой
    safeSendMessage({
      type: 'UPDATE_STATISTICS',
      data: {
        totalScans: 1,
        loadsFound: newLoadsFound,
        profitableLoads: profitableLoadsFound,
        lastActive: Date.now()
      }
    }).catch(error => {
      console.debug('Stats update failed:', error.message);
    });
    
  } catch (error) {
    console.error('Error during load scanning:', error);
    adjustScanInterval('error');
  }
}

// Очистка кеша найденных грузов
function cleanupFoundLoadsCache() {
  if (monitoringState.foundLoads.size <= 100) {
    return; // Кеш еще небольой
  }
  
  const now = Date.now();
  const maxAge = 30 * 60 * 1000; // 30 минут
  const maxSize = 50; // Максимальный размер кеша
  
  const entries = Array.from(monitoringState.foundLoads.entries());
  
  // Удаляем старые записи
  const freshEntries = entries.filter(([id, load]) => {
    return (now - load.foundAt) < maxAge;
  });
  
  // Если все еще много записей, оставляем только самые новые
  if (freshEntries.length > maxSize) {
    freshEntries.sort((a, b) => b[1].foundAt - a[1].foundAt);
    freshEntries.splice(maxSize);
  }
  
  // Пересоздаем Map с очищенными данными
  monitoringState.foundLoads.clear();
  freshEntries.forEach(([id, load]) => {
    monitoringState.foundLoads.set(id, load);
  });
  
  console.log(`Cache cleaned: ${entries.length} -> ${freshEntries.length} entries`);
}

// Проверка, находимся ли на странице поиска грузов
function isOnLoadSearchPage() {
  const url = window.location.href;
  
  // Проверяем URL
  const validPaths = [
    '/search',
    '/loads',
    '/freight',
    '/board',
    '/loadboard'
  ];
  
  const isValidPath = validPaths.some(path => url.includes(path));
  
  // Проверяем наличие элементов страницы поиска
  const searchIndicators = [
    document.querySelector('[class*="search"]'),
    document.querySelector('[class*="load"]'),
    document.querySelector('[class*="freight"]'),
    document.querySelector('input[type="submit"], button[type="submit"]'),
    document.querySelector('[class*="filter"]'),
    document.querySelector('[class*="result"]')
  ];
  
  const hasSearchElements = searchIndicators.some(el => el !== null);
  
  return isValidPath || hasSearchElements;
}

// Переход на страницу поиска грузов
function navigateToLoadSearchPage() {
  console.log('🚀 Переходим на страницу поиска грузов...');
  
  // Пробуем найти ссылку на поиск грузов
  const searchLinks = [
    'a[href*="search"]',
    'a[href*="loads"]',
    'a[href*="freight"]',
    'a[href*="board"]',
    '[class*="search"] a',
    '[class*="load"] a',
    '[class*="freight"] a'
  ];
  
  for (const selector of searchLinks) {
    const link = document.querySelector(selector);
    if (link) {
      console.log(`🔗 Найдена ссылка на поиск: ${selector}`);
      link.click();
      return;
    }
  }
  
  // Если не нашли ссылку, пробуем перейти по прямому URL
  const baseUrl = window.location.origin;
  const searchPaths = [
    '/search',
    '/loads',
    '/freight-board',
    '/loadboard'
  ];
  
  for (const path of searchPaths) {
    try {
      window.location.href = baseUrl + path;
      return;
    } catch (error) {
      console.warn(`Не удалось перейти на ${path}:`, error);
    }
  }
}

// Попытка обновить поиск
function attemptRefreshSearch() {
  console.log('🔄 Попытка обновить поиск...');
  
  // Пробуем найти кнопку поиска/обновления
  const searchButtons = [
    'button[type="submit"]',
    'input[type="submit"]',
    '[class*="search"][class*="button"]',
    '[class*="search-btn"]',
    '[class*="refresh"]',
    '[class*="reload"]',
    'button:contains("Search")',
    'button:contains("Поиск")',
    'button:contains("Найти")'
  ];
  
  for (const selector of searchButtons) {
    try {
      const button = document.querySelector(selector);
      if (button && !button.disabled) {
        console.log(`🔍 Нажимаем кнопку поиска: ${selector}`);
        button.click();
        return true;
      }
    } catch (error) {
      console.warn(`Ошибка при нажатии кнопки ${selector}:`, error);
    }
  }
  
  // Если кнопка не найдена, пробуем форму
  const searchForms = document.querySelectorAll('form');
  for (const form of searchForms) {
    try {
      const formText = form.textContent.toLowerCase();
      if (formText.includes('search') || formText.includes('поиск') || formText.includes('load')) {
        console.log('📝 Отправляем форму поиска');
        form.submit();
        return true;
      }
    } catch (error) {
      console.warn('Ошибка отправки формы:', error);
    }
  }
  
  // Последняя попытка - обновить страницу
  console.log('🔄 Обновляем страницу');
  window.location.reload();
  return false;
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

// Определение типа сайта для выбора стратегии парсинга
function detectSiteType() {
  const url = window.location.href.toLowerCase();
  const hostname = window.location.hostname.toLowerCase();
  
  if (hostname.includes('lothian') || url.includes('lothian')) {
    return 'lothian';
  }
  if (hostname.includes('freightpower') || url.includes('freightpower')) {
    return 'freightpower';
  }
  
  // Определение Ionic приложений
  const ionicIndicators = [
    document.querySelector('ion-app'),
    document.querySelector('ion-content'),
    document.querySelector('ion-grid'),
    document.querySelector('ion-row'),
    document.querySelector('ion-col'),
    document.querySelector('[class*="ionic"]'),
    window.Ionic !== undefined
  ];
  
  const isIonic = ionicIndicators.some(indicator => !!indicator);
  if (isIonic) {
    console.log('🔷 Detected Ionic application');
    return 'ionic';
  }
  
  return 'unknown';
}

// Новая функция парсинга для LOTHIAN с правильными селекторами
function parseLothianCard(element) {
  console.log('🚛 Парсинг LOTHIAN карточки с селекторами...', element);
  
  // Проверка валидности элемента
  if (!element || !element.textContent) {
    console.error('❌ Invalid Lothian element');
    return null;
  }
  
  const loadData = {
    id: null,
    capacityType: 'Power Only', // По умолчанию для LOTHIAN
    pickup: null,
    delivery: null,
    pickupDate: null,
    deliveryDate: null,
    miles: 0,
    deadhead: 0,
    rate: 0,
    weight: null,
    originRadius: null,
    destinationRadius: null,
    element: element
  };
  
  try {
    // 1. ID - селектор .card_p-elements.loadno_card
    const idElement = element.querySelector('.card_p-elements.loadno_card');
    if (idElement) {
      const idText = idElement.textContent.trim();
      // Извлекаем числовой ID
      const idMatch = idText.match(/\b(\d{8,12})\b/);
      if (idMatch) {
        loadData.id = idMatch[1];
        console.log('🆔 ID найден через селектор:', loadData.id);
      }
    }
    
    // 2. Тип оборудования - селектор .capacity-type.capacity-type-font
    const typeElement = element.querySelector('.capacity-type.capacity-type-font');
    if (typeElement) {
      loadData.capacityType = typeElement.textContent.trim() || 'Power Only';
      console.log('🚚 Тип найден через селектор:', loadData.capacityType);
    }
    
    // 3. Мили - селектор .card-distance[data-testid="card-distance"]
    const milesElement = element.querySelector('.card-distance[data-testid="card-distance"]');
    if (milesElement) {
      const milesText = milesElement.textContent.trim();
      const milesMatch = milesText.match(/(\d+)\s*mi(?:les?)?/i);
      if (milesMatch) {
        loadData.miles = parseInt(milesMatch[1]);
        console.log('📏 Мили найдены через селектор:', loadData.miles);
      }
    }
    
    // 4. Вес - селектор .card_p-elements.card-lbs
    const weightElement = element.querySelector('.card_p-elements.card-lbs');
    if (weightElement) {
      const weightText = weightElement.textContent.trim();
      const weightMatch = weightText.match(/(\d{1,3}(?:,\d{3})*)\s*lbs/i);
      if (weightMatch) {
        loadData.weight = parseInt(weightMatch[1].replace(/,/g, ''));
        console.log('⚖️ Вес найден через селектор:', loadData.weight, 'lbs');
      }
    }
    
    // 5. Локации - селектор .origin_city (первый - откуда, второй - куда)
    const locationElements = element.querySelectorAll('.origin_city');
    if (locationElements.length >= 2) {
      loadData.pickup = locationElements[0].textContent.trim();
      loadData.delivery = locationElements[1].textContent.trim();
      console.log('📍 Локации найдены через селекторы:', {
        pickup: loadData.pickup,
        delivery: loadData.delivery
      });
    } else if (locationElements.length === 1) {
      // Если найден только один элемент, используем его как pickup
      loadData.pickup = locationElements[0].textContent.trim();
      console.log('📍 Найдена только одна локация:', loadData.pickup);
    }
    
    // 6. Deadhead - ищем в p.origin_dateTime, где текст содержит "Deadhead"
    const dateTimeElements = element.querySelectorAll('p.origin_dateTime');
    for (const elem of dateTimeElements) {
      const text = elem.textContent || '';
      if (text.includes('Deadhead')) {
        const deadheadMatch = text.match(/Deadhead\s+(\d+)\s*mi/i);
        if (deadheadMatch) {
          loadData.deadhead = parseInt(deadheadMatch[1]);
          console.log('🚚 Deadhead найден:', loadData.deadhead, 'mi');
          break;
        }
      }
    }
    
    // 7. Ставка - пытаемся найти через различные селекторы
    const rateSelectors = [
      '.rate-amount',
      '.card-price',
      '[class*="rate"]',
      '[class*="price"]'
    ];
    
    for (const selector of rateSelectors) {
      const rateElement = element.querySelector(selector);
      if (rateElement) {
        const rateText = rateElement.textContent.trim();
        const rateMatch = rateText.match(/\$\s*(\d{1,6}(?:,\d{3})*(?:\.\d{2})?)/);
        if (rateMatch) {
          loadData.rate = parseFloat(rateMatch[1].replace(/,/g, ''));
          console.log('💰 Ставка найдена через селектор', selector + ':', loadData.rate);
          break;
        }
      }
    }
    
    // 8. Если ставка не найдена через селекторы, ищем в тексте всего элемента
    if (loadData.rate === 0) {
      const fullText = element.textContent || '';
      const rateMatch = fullText.match(/\$\s*(\d{1,6})/);
      if (rateMatch) {
        loadData.rate = parseFloat(rateMatch[1]);
        console.log('💰 Ставка найдена в тексте:', loadData.rate);
      }
    }
    
    // 9. Даты - пытаемся извлечь из элементов с датами
    const dateElements = element.querySelectorAll('.origin_dateTime, [class*="date"]');
    const dates = [];
    for (const elem of dateElements) {
      const text = elem.textContent || '';
      const dateMatch = text.match(/(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}/i);
      if (dateMatch && !text.includes('Deadhead')) {
        dates.push(dateMatch[0]);
      }
    }
    
    if (dates.length >= 2) {
      loadData.pickupDate = dates[0];
      loadData.deliveryDate = dates[1];
      console.log('📅 Даты найдены:', {
        pickup: loadData.pickupDate,
        delivery: loadData.deliveryDate
      });
    }
    
  } catch (error) {
    console.error('❌ Ошибка при парсинге LOTHIAN карточки:', error);
  }
  
  // Валидация данных - используем глобальную функцию hasMinimalData
  // Но сначала генерируем ID если его нет
  if (!loadData.id) {
    loadData.id = generateLoadId(loadData);
  }
  
  if (!window.hasMinimalData(loadData)) {
    console.warn('⚠️ LOTHIAN карточка не содержит достаточно данных');
    return null;
  }
  
  // Проверяем разумность значений
  if (loadData.miles > 5000) {
    console.warn('⚠️ Подозрительно большое расстояние:', loadData.miles);
    loadData.miles = 0;
  }
  
  if (loadData.rate > 50000) {
    console.warn('⚠️ Подозрительно большая ставка:', loadData.rate);
    loadData.rate = 0;
  }
  
  if (loadData.deadhead > 250) {
    console.warn('⚠️ Подозрительно большой deadhead:', loadData.deadhead);
    loadData.deadhead = 0;
  }
  
  console.log('✅ LOTHIAN карточка успешно распарсена:', loadData);
  return loadData;
}

// Специальный парсинг для LOTHIAN
function parseLoadElementLothian(element) {
  const card = getCardRoot(element) || element;
  if (!card) return null;

  const getText = (sel) => card.querySelector(sel)?.textContent?.trim() || '';
  const getAll = (sel) => Array.from(card.querySelectorAll(sel));

  const idText = getText('.card_p-elements.loadno_card');
  const id = (idText.match(/\b\d{8,12}\b/) || [null])[0];

  const capacityType = getText('.capacity-type.capacity-type-font') || null;

  const milesText = getText('.card-distance[data-testid="card-distance"]');
  const miles = milesText ? parseInt(milesText.replace(/[^\d]/g, ''), 10) || 0 : 0;

  const weight = getText('.card_p-elements.card-lbs') || null;

  const cities = getAll('.origin_city').map(n => n.textContent.trim()).filter(Boolean);
  const pickup = cities[0] || null;
  const delivery = cities[1] || null;

  const deadheadText = getAll('p.origin_dateTime, .origin_dateTime')
    .map(n => n.textContent.trim())
    .find(t => /Deadhead/i.test(t)) || '';
  const deadhead = (deadheadText.match(/Deadhead\s+(\d+)\s*mi/i) || [0, 0])[1] | 0;

  const fullText = card.textContent || '';
  const rateMatch = fullText.match(/\$\s*([\d,]+(?:\.\d{2})?)(?=\D|$)/);
  const rate = rateMatch ? parseFloat(rateMatch[1].replace(/,/g, '')) : 0;

  // Валидации
  const validRate = rate >= 50 && rate <= 50000 ? rate : 0;
  const validMiles = miles >= 1 && miles <= 5000 ? miles : 0;
  const validDeadhead = deadhead >= 0 && deadhead <= 1000 ? deadhead : 0;

  if (!id || !pickup || !delivery) {
    console.debug('LOTHIAN: не хватает обязательных полей', { id, pickup, delivery });
    return null;
  }

  return {
    id,
    capacityType,
    pickup,
    delivery,
    pickupDate: null,
    deliveryDate: null,
    miles: validMiles,
    deadhead: validDeadhead,
    rate: validRate,
    weight,
    originRadius: null,
    destinationRadius: null,
    element: card
  };
}

// Функция для создания отладочного отчета
function createDebugReport() {
  const siteType = detectSiteType();
  const report = {
    siteType: siteType,
    url: window.location.href,
    timestamp: new Date().toISOString(),
    loadElements: [],
    selectors: SELECTORS,
    parsing_results: []
  };
  
  console.log('🔧 Создание отладочного отчета для', siteType);
  
  // Находим элементы грузов
  const loadElements = findLoadElements();
  report.loadElements = loadElements.map((el, index) => ({
    index: index,
    tagName: el.tagName,
    className: el.className,
    textContent: el.textContent?.substring(0, 200) + '...',
    outerHTML: el.outerHTML.substring(0, 500) + '...'
  }));
  
  // Пробуем парсить первые 3 элемента
  for (let i = 0; i < Math.min(3, loadElements.length); i++) {
    try {
      const element = loadElements[i];
      const loadData = parseLoadElement(element);
      report.parsing_results.push({
        element_index: i,
        success: true,
        data: loadData
      });
    } catch (error) {
      report.parsing_results.push({
        element_index: i,
        success: false,
        error: error.message
      });
    }
  }
  
  console.log('📋 Отладочный отчет:', report);
  return report;
}

// Добавляем функцию в глобальный объект для вызова из консоли
window.freightDebugReport = createDebugReport;

// Тестовая функция для LOTHIAN
function testLothianParsing() {
  console.log('🧪 Тестирование парсинга LOTHIAN...');
  
  // Создаем тестовый элемент с данными LOTHIAN
  const testHTML = `
    <tr>
      <td>4007568993</td>
      <td>Power Only</td>
      <td>29 miles</td>
      <td>43,373 lbs</td>
      <td>IRVING, TX</td>
      <td>Aug 22 6:30am - Aug 24 8:59am</td>
      <td>Drop Empty Trailer, Pick Up Loaded Trailer</td>
      <td>Deadhead 20 mi</td>
      <td>LANCASTER, TX</td>
      <td>Aug 24 9:00am - 9:00am</td>
      <td>Live Unload</td>
    </tr>
  `;
  
  const testElement = document.createElement('div');
  testElement.innerHTML = testHTML;
  const trElement = testElement.firstElementChild;
  
  console.log('📄 Тестовый элемент создан:', trElement);
  
  try {
    const result = parseLoadElementLothian(trElement);
    console.log('✅ Результат тестирования:', result);
    
    // Проверяем что основные поля заполнены
    const checks = {
      hasId: !!result.id,
      hasPickup: !!result.pickup && result.pickup !== 'Неизвестно',
      hasDelivery: !!result.delivery && result.delivery !== 'Неизвестно',
      hasMiles: result.miles > 0,
      hasDeadhead: result.deadhead >= 0,
      hasRate: result.rate >= 0
    };
    
    console.log('🔍 Проверки:', checks);
    
    const passedChecks = Object.values(checks).filter(Boolean).length;
    const totalChecks = Object.keys(checks).length;
    
    console.log(`📊 Пройдено проверок: ${passedChecks}/${totalChecks}`);
    
    if (passedChecks >= 4) {
      console.log('✅ Тест прошел успешно!');
    } else {
      console.log('❌ Тест провален, нужны улучшения');
    }
    
    return result;
    
  } catch (error) {
    console.error('❌ Ошибка в тестировании:', error);
    return null;
  }
}

// Добавляем тестовую функцию в глобальный объект
window.testLothianParsing = testLothianParsing;

// Новая тестовая функция для parseLothianCard
function testLothianCardParsing() {
  console.log('🧪 Тестирование нового парсинга LOTHIAN карточек...');
  
  // Создаем тестовый HTML с правильной структурой LOTHIAN
  const testHTML = `
    <div class="load-card">
      <div class="card_p-elements loadno_card">Load #4007568993</div>
      <div class="capacity-type capacity-type-font">Power Only</div>
      <div class="card-distance" data-testid="card-distance">29 miles</div>
      <div class="card_p-elements card-lbs">43,373 lbs</div>
      <div class="origin_city">IRVING, TX</div>
      <div class="origin_city">LANCASTER, TX</div>
      <p class="origin_dateTime load_header_elements stop-appointment">Deadhead 20 mi</p>
      <div class="origin_dateTime">Aug 22 6:30am - Aug 24 8:59am</div>
      <div class="origin_dateTime">Aug 24 9:00am - 9:00am</div>
      <div class="rate-amount">$850</div>
    </div>
  `;
  
  const testElement = document.createElement('div');
  testElement.innerHTML = testHTML;
  const cardElement = testElement.firstElementChild;
  
  console.log('📄 Тестовый элемент создан');
  
  try {
    const result = parseLothianCard(cardElement);
    console.log('✅ Результат парсинга:', result);
    
    // Проверяем правильность результатов
    const expectedResults = {
      id: '4007568993',
      capacityType: 'Power Only',
      miles: 29,
      weight: 43373,
      pickup: 'IRVING, TX',
      delivery: 'LANCASTER, TX',
      deadhead: 20,
      rate: 850
    };
    
    const checks = {
      'ID корректный': result && result.id === expectedResults.id,
      'Тип корректный': result && result.capacityType === expectedResults.capacityType,
      'Мили корректные': result && result.miles === expectedResults.miles,
      'Вес корректный': result && result.weight === expectedResults.weight,
      'Откуда корректно': result && result.pickup === expectedResults.pickup,
      'Куда корректно': result && result.delivery === expectedResults.delivery,
      'Deadhead корректный': result && result.deadhead === expectedResults.deadhead,
      'Ставка корректная': result && result.rate === expectedResults.rate
    };
    
    console.log('🔍 Проверки:');
    Object.entries(checks).forEach(([check, passed]) => {
      console.log(`  ${passed ? '✅' : '❌'} ${check}`);
    });
    
    console.log('📊 Ожидаемые результаты:', expectedResults);
    console.log('📊 Фактические результаты:', result ? {
      id: result.id,
      capacityType: result.capacityType,
      miles: result.miles,
      weight: result.weight,
      pickup: result.pickup,
      delivery: result.delivery,
      deadhead: result.deadhead,
      rate: result.rate
    } : 'null');
    
    const passedChecks = Object.values(checks).filter(Boolean).length;
    const totalChecks = Object.keys(checks).length;
    
    console.log(`\n📊 Пройдено проверок: ${passedChecks}/${totalChecks}`);
    
    if (passedChecks === totalChecks) {
      console.log('✅ Тест прошел успешно! Все данные извлечены правильно.');
    } else {
      console.log('❌ Тест не пройден, некоторые данные извлечены неправильно.');
    }
    
    return result;
    
  } catch (error) {
    console.error('❌ Ошибка в тестировании:', error);
    return null;
  }
}

// Добавляем новую тестовую функцию в глобальный объект
window.testLothianCardParsing = testLothianCardParsing;

// Тестовая функция для Ionic
function testIonicParsing() {
  console.log('🧪 Тестирование парсинга Ionic...');
  
  // Создаем тестовый элемент с данными из примера
  const testHTML = `
    <ion-row class="load-item">
      4007567920Power Only$909521 miles26,000 lbsHigh ValueDALLAS, TXAug 26 12:01am - 1:00amDrop Empty Trailer, Pick Up Loaded TrailerBIRMINGHAM, MOAug 26 12:31am - 12:00pm
    </ion-row>
  `;
  
  const testElement = document.createElement('div');
  testElement.innerHTML = testHTML;
  const ionElement = testElement.firstElementChild;
  
  console.log('📄 Тестовый Ionic элемент создан:', ionElement);
  
  try {
    const result = parseLoadElementIonic(ionElement);
    console.log('✅ Результат парсинга Ionic:', result);
    
    // Проверяем правильность результатов
    const expectedResults = {
      id: '4007567920',
      capacityType: 'Power Only',
      rate: 909,
      miles: 521,
      pickup: 'DALLAS, TX',
      delivery: 'BIRMINGHAM, MO',
      weight: 26000
    };
    
    const checks = {
      idCorrect: result.id === expectedResults.id,
      typeCorrect: result.capacityType === expectedResults.capacityType,
      rateCorrect: result.rate === expectedResults.rate,
      milesCorrect: result.miles === expectedResults.miles,
      pickupCorrect: result.pickup === expectedResults.pickup,
      deliveryCorrect: result.delivery === expectedResults.delivery,
      weightCorrect: result.weight === expectedResults.weight
    };
    
    console.log('🔍 Проверки:', checks);
    console.log('📊 Ожидаемые результаты:', expectedResults);
    console.log('📊 Фактические результаты:', {
      id: result.id,
      capacityType: result.capacityType,
      rate: result.rate,
      miles: result.miles,
      pickup: result.pickup,
      delivery: result.delivery,
      weight: result.weight
    });
    
    const passedChecks = Object.values(checks).filter(Boolean).length;
    const totalChecks = Object.keys(checks).length;
    
    console.log(`📊 Пройдено проверок: ${passedChecks}/${totalChecks}`);
    
    if (passedChecks === totalChecks) {
      console.log('✅ Тест прошел успешно! Все данные извлечены правильно.');
    } else {
      console.log('❌ Тест не пройден, некоторые данные извлечены неправильно.');
    }
    
    return result;
    
  } catch (error) {
    console.error('❌ Ошибка в тестировании Ionic:', error);
    return null;
  }
}

// Добавляем тестовую функцию Ionic в глобальный объект
window.testIonicParsing = testIonicParsing;

// Специальный парсинг для Ionic приложений
function parseLoadElementIonic(element) {
  console.log('🔷 Парсинг Ionic элемента...', element);
  
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
    weight: null,
    originRadius: null,
    destinationRadius: null,
    element: element
  };
  
  const fullText = element.textContent || '';
  console.log('📝 Полный текст Ionic элемента:', fullText);
  
  // Специальные регулярные выражения для парсинга строки Ionic
  // Пример: "4007567920Power Only$909521 miles26,000 lbsHigh ValueDALLAS, TXAug 26 12:01am - 1:00amDrop Empty Trailer, Pick Up Loaded TrailerBIRMINGHAM, MOAug 26 12:31am - 12:00pm"
  
  // ID груза (числа в начале строки, обычно 10+ цифр)
  const idMatch = fullText.match(/^(\d{10,})/);
  if (idMatch) {
    loadData.id = idMatch[1];
    console.log('🆔 Найден ID:', loadData.id);
  }
  
  // Тип груза (после ID, перед $)
  const typeMatch = fullText.match(/^\d*([A-Za-z\s]+)\$/);
  if (typeMatch) {
    loadData.capacityType = typeMatch[1].trim();
    console.log('🚚 Найден тип:', loadData.capacityType);
  }
  
  // Ставка ($ + число, но не включая следующие цифры миль)
  const rateMatch = fullText.match(/\$(\d{1,4})(?=\d+\s|[a-zA-Z])/);
  if (rateMatch) {
    loadData.rate = parseFloat(rateMatch[1]);
    console.log('💰 Найдена ставка:', loadData.rate);
  }
  
  // Мили (число перед "miles")
  const milesMatch = fullText.match(/(\d{1,4})\s*miles/i);
  if (milesMatch) {
    loadData.miles = parseInt(milesMatch[1]);
    console.log('📏 Найдены мили:', loadData.miles);
  }
  
  // Deadhead (если есть)
  const deadheadMatch = fullText.match(/deadhead\s*(\d+)\s*mi/i);
  if (deadheadMatch) {
    loadData.deadhead = parseInt(deadheadMatch[1]);
    console.log('🚚 Найден deadhead:', loadData.deadhead);
  }
  
  // Вес груза (если есть)
  const weightMatch = fullText.match(/(\d{1,3}(?:,\d{3})*)\s*lbs/i);
  if (weightMatch) {
    const weight = weightMatch[1].replace(/,/g, '');
    loadData.weight = parseInt(weight);
    console.log('⚖️ Найден вес:', loadData.weight, 'lbs');
  }
  
  // Локации (ГОРОД, ШТАТ)
  const locationPattern = /([A-Z][A-Z\s]+),\s*([A-Z]{2})/g;
  const locations = [...fullText.matchAll(locationPattern)];
  
  if (locations.length >= 2) {
    loadData.pickup = `${locations[0][1].trim()}, ${locations[0][2]}`;
    loadData.delivery = `${locations[1][1].trim()}, ${locations[1][2]}`;
    console.log('📍 Найдены локации:', { pickup: loadData.pickup, delivery: loadData.delivery });
  }
  
  // Даты (формат: Aug 26 12:01am)
  const datePattern = /(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}\s+\d{1,2}:\d{2}[ap]m/gi;
  const dates = [...fullText.matchAll(datePattern)];
  
  if (dates.length > 0) {
    loadData.pickupDate = dates[0][0];
    if (dates.length > 1) {
      loadData.deliveryDate = dates[1][0];
    }
    console.log('📅 Найдены даты:', { pickup: loadData.pickupDate, delivery: loadData.deliveryDate });
  }
  
  // Если не удалось найти данные в одной строке, пробуем альтернативный поиск
  if (!loadData.rate || loadData.rate === 0) {
    // Ищем цену в дочерних элементах
    const priceElement = element.querySelector('p.card-price, .card-price, [class*="price"]');
    if (priceElement) {
      const priceText = priceElement.textContent || '';
      loadData.rate = parseNumberImproved(priceText, 'rate');
    }
  }
  
  // Генерируем ID если его нет
  if (!loadData.id) {
    loadData.id = generateLoadId(loadData);
  }
  
  console.log('✅ Ionic груз распарсен:', loadData);
  return loadData;
}

// Парсинг данных груза из элемента (улучшенная версия)
function parseLoadElement(element) {
  const siteType = detectSiteType();
  let load = null;

  if (siteType === 'freightpower') {
    load = parseLoadElementLothian(element);
  } else if (siteType === 'ionic') {
    load = parseLoadElementIonic(element);
  }

  if (!load || !load.pickup || !load.delivery) {
    const text = (getCardRoot(element) || element)?.textContent || '';
    const fallback = parseLoadFromText(text);
    if (fallback?.pickup && fallback?.delivery) {
      load = { ...fallback, element: getCardRoot(element) || element };
    }
  }
  // Валидация с использованием hasMinimalData
  if (!load || !window.hasMinimalData(load)) {
    return null;
  }

  return load;
}  
  // Дополнительные попытки найти ID
  if (!extractedId) {
    const idCandidates = [
      element.querySelector('[data-load-id]')?.getAttribute('data-load-id'),
      element.querySelector('[id]')?.getAttribute('id'),
      element.dataset?.loadId,
      element.dataset?.id
    ].filter(Boolean);
    
    extractedId = idCandidates[0];
  }
  
  // Фильтруем некорректные ID
  if (extractedId && (
    extractedId.toLowerCase().includes('dlefield') ||
    extractedId.toLowerCase().includes('field') ||
    extractedId.toLowerCase().includes('placeholder') ||
    extractedId.toLowerCase().includes('enter') ||
    extractedId.toLowerCase().includes('select') ||
    extractedId.length < 3 ||
    extractedId.length > 50
  )) {
    extractedId = null;
  }
  
  // Улучшенное извлечение мест погрузки/разгрузки
  loadData.pickup = extractLocationText(element, SELECTORS.pickup_location, 'pickup');
  loadData.delivery = extractLocationText(element, SELECTORS.delivery_location, 'delivery');
  
  // Если не удалось найти pickup/delivery через селекторы, используем heuristic search
  if (!loadData.pickup || !loadData.delivery) {
    const locations = extractLocationsHeuristic(element);
    if (locations.pickup && !loadData.pickup) loadData.pickup = locations.pickup;
    if (locations.delivery && !loadData.delivery) loadData.delivery = locations.delivery;
  }
  
  // Извлекаем тип груза
  loadData.capacityType = extractText(element, SELECTORS.capacity_type) || 'Сухой фургон';
  
  // Извлекаем даты
  loadData.pickupDate = extractText(element, SELECTORS.pickup_date);
  loadData.deliveryDate = extractText(element, SELECTORS.delivery_date);
  
  // Улучшенное извлечение числовых данных
  const milesText = extractText(element, SELECTORS.miles);
  loadData.miles = parseNumberImproved(milesText, 'miles');
  
  const deadheadText = extractText(element, SELECTORS.deadhead);
  loadData.deadhead = parseNumberImproved(deadheadText, 'deadhead');
  
  const rateText = extractText(element, SELECTORS.rate);
  loadData.rate = parseNumberImproved(rateText, 'rate');
  
  // Если мили = 0, попробуем найти их другими способами
  if (loadData.miles === 0) {
    loadData.miles = findMilesAlternative(element);
  }
  
  // Если rate = 0, попробуем найти ставку другими способами
  if (loadData.rate === 0) {
    loadData.rate = findRateAlternative(element);
  }
  
  // Извлекаем радиусы
  const radiusElements = element.querySelectorAll(SELECTORS.radius.join(', '));
  if (radiusElements.length >= 2) {
    loadData.originRadius = extractRadius(radiusElements[0]);
    loadData.destinationRadius = extractRadius(radiusElements[1]);
  }
  
  // Генерируем ID если его нет
  loadData.id = extractedId || generateLoadId(loadData);
  
  // Валидация данных
  if (!loadData.pickup || !loadData.delivery) {
    console.warn('❌ Отсутствуют обязательные данные (pickup/delivery):', JSON.stringify({
      pickup: loadData.pickup,
      delivery: loadData.delivery,
      elementHTML: element.innerHTML.substring(0, 200)
    }, null, 2));
    return null;
  }
  
  // Финальная проверка корректности данных
  if (loadData.miles > 5000 || loadData.rate > 50000) {
    console.warn('⚠️ Подозрительно большие значения:', JSON.stringify({
      id: loadData.id,
      miles: loadData.miles,
      rate: loadData.rate,
      milesText: milesText,
      rateText: rateText,
      deadheadText: deadheadText
    }, null, 2));
    
    // Если значения явно неправильные, сбрасываем их
    if (loadData.miles > 5000) {
      console.log('🔧 Сброс неправильных миль:', loadData.miles, '-> 0');
      loadData.miles = 0;
    }
    if (loadData.rate > 50000) {
      console.log('🔧 Сброс неправильной ставки:', loadData.rate, '-> 0');
      loadData.rate = 0;
    }
  }
  
  console.log('✅ Груз успешно распарсен:', JSON.stringify({
    id: loadData.id,
    pickup: loadData.pickup,
    delivery: loadData.delivery,
    miles: loadData.miles,
    rate: loadData.rate
  }, null, 2));
  
  return loadData;
}

// Генерация уникального ID для груза
function generateLoadId(data) {
  try {
    let idParts = [];
    
    // Добавляем части местоположений (первые слова)
    if (data.pickup) {
      const pickupPart = data.pickup.split(/[,\s]+/)[0]?.substring(0, 8) || 'pickup';
      idParts.push(pickupPart);
    }
    
    if (data.delivery) {
      const deliveryPart = data.delivery.split(/[,\s]+/)[0]?.substring(0, 8) || 'delivery';
      idParts.push(deliveryPart);
    }
    
    // Добавляем миль для уникальности
    if (data.miles > 0) {
      idParts.push(`${data.miles}mi`);
    }
    
    // Добавляем ставку для уникальности
    if (data.rate > 0) {
      idParts.push(`$${Math.round(data.rate)}`);
    }
    
    // Добавляем временную метку
    const timestamp = Date.now().toString().slice(-6); // Последние 6 цифр
    idParts.push(timestamp);
    
    // Создаем ID
    const generatedId = idParts.join('-').replace(/[^\w\-$]/g, '');
    
    console.log('🔧 Generated load ID:', generatedId, 'from data:', JSON.stringify({
      pickup: data.pickup,
      delivery: data.delivery,
      miles: data.miles,
      rate: data.rate
    }, null, 2));
    
    return generatedId;
    
  } catch (error) {
    console.error('Error generating load ID:', error);
    // Fallback ID
    return `load-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }
}

// Улучшенное извлечение текста местоположения
function extractLocationText(element, selectors, type) {
  const text = extractText(element, selectors);
  if (!text) return null;
  
  // Очищаем и валидируем местоположение
  const cleaned = text.trim()
    .replace(/^(Origin|Destination|Pickup|Delivery):\s*/i, '')
    .replace(/\s+/g, ' ');
  
  // Проверяем что это похоже на местоположение (содержит город/штат)
  if (cleaned.length < 3 || cleaned.length > 100) return null;
  if (/^[^a-zA-Z]*$/.test(cleaned)) return null; // Только цифры/символы
  
  return cleaned;
}

// Эвристическое извлечение местоположений
function extractLocationsHeuristic(element) {
  const text = element.textContent || '';
  const locations = { pickup: null, delivery: null };
  
  // Паттерны для поиска местоположений
  const locationPatterns = [
    // Город, Штат ZIP
    /([A-Z][a-z]+(?:\s+[A-Z][a-z]*)*),\s*([A-Z]{2})\s*(\d{5})?/g,
    // Город Штат
    /([A-Z][a-z]+(?:\s+[A-Z][a-z]*)*)\s+([A-Z]{2})\b/g,
    // Простые города
    /\b([A-Z][a-z]+(?:ville|ton|burg|city|town|field))\b/g
  ];
  
  for (const pattern of locationPatterns) {
    const matches = [...text.matchAll(pattern)];
    if (matches.length >= 2) {
      locations.pickup = matches[0][0];
      locations.delivery = matches[1][0];
      break;
    } else if (matches.length === 1 && !locations.pickup) {
      locations.pickup = matches[0][0];
    }
  }
  
  return locations;
}

// Улучшенный парсинг чисел
function parseNumberImproved(text, type) {
  if (!text) return 0;
  
  console.log(`🔢 Парсинг ${type}: "${text}"`);
  
  let result = 0;
  
  // Определяем разумные диапазоны для каждого типа
  const ranges = {
    rate: { min: 50, max: 1000000 }, // Увеличиваем максимум для обработки центов
    price: { min: 50, max: 1000000 }, // Увеличиваем максимум для обработки центов
    miles: { min: 1, max: 5000 },
    distance: { min: 1, max: 5000 },
    deadhead: { min: 0, max: 250 }
  };
  
  // Специальная обработка для разных типов
  if (type === 'rate' || type === 'price') {
    // Ищем числа с знаком доллара - берем ПЕРВОЕ число после $
    // Например, из "$761413 miles" берем только 761
    const rateMatch = text.match(/\$\s*(\d{1,6})/);
    if (rateMatch) {
      result = parseFloat(rateMatch[1]);
      console.log(`💵 Извлечена ставка: $${result} из "${text}"`);
    } else {
      // Если нет $, ищем отдельные элементы с долларом
      const dollarMatch = text.match(/\$\s*(\d+(?:,\d{3})*(?:\.\d{2})?)/);
      if (dollarMatch) {
        const cleaned = dollarMatch[1].replace(/,/g, '');
        result = parseFloat(cleaned);
      }
    }
  } else if (type === 'miles' || type === 'distance') {
    // Ищем числа со словом "miles" или "mi"
    const milesMatch = text.match(/(\d+(?:,\d{3})*)\s*(?:miles?|mi)/i);
    if (milesMatch) {
      const cleaned = milesMatch[1].replace(/,/g, '');
      result = parseFloat(cleaned);
    } else {
      // Ищем просто числа в разумных пределах для миль
      const numbers = text.match(/(\d+(?:,\d{3})*)/g);
      if (numbers) {
        for (const num of numbers) {
          const cleaned = num.replace(/,/g, '');
          const parsed = parseFloat(cleaned);
          if (parsed >= ranges.miles.min && parsed <= ranges.miles.max) {
            result = parsed;
            break;
          }
        }
      }
    }
  } else if (type === 'deadhead') {
    // Ищем ТОЛЬКО числа в строке "Deadhead XX mi"
    const deadheadMatch = text.match(/Deadhead\s+(\d+)\s*mi/i);
    if (deadheadMatch) {
      result = parseFloat(deadheadMatch[1]);
      console.log(`🚚 Извлечен deadhead: ${result} mi из "${text}"`);
    }
    // Если не нашли, результат остается 0
  } else {
    // Общий парсинг для других типов
    const cleaned = text.replace(/[^\d\.,]/g, '');
    
    // Обрабатываем запятые как разделители тысяч
    if (cleaned.includes(',')) {
      const parts = cleaned.split(',');
      if (parts.length === 2 && parts[1].length <= 2) {
        // Запятая как десятичный разделитель
        const finalCleaned = parts[0] + '.' + parts[1];
        result = parseFloat(finalCleaned);
      } else {
        // Запятые как разделители тысяч
        const finalCleaned = cleaned.replace(/,/g, '');
        result = parseFloat(finalCleaned);
      }
    } else {
      result = parseFloat(cleaned);
    }
  }
  
  result = isNaN(result) ? 0 : result;
  
  // Проверяем диапазоны и выдаем предупреждение если значение вне диапазона
  const range = ranges[type];
  if (range && result > 0) {
    if (result < range.min || result > range.max) {
      console.warn(`⚠️ ${type} вне ожидаемого диапазона [${range.min}-${range.max}]: ${result}`);
      // Для Ionic приложений не сбрасываем значения, так как может быть специфичный формат
      if (detectSiteType() !== 'ionic') {
        result = 0;
      }
    }
    
    // Если это rate или price и значение слишком большое, возможно это центы
    // НО: не конвертируем, если уже извлекли правильное значение
    if ((type === 'rate' || type === 'price') && result > 50000) {
      console.warn(`⚠️ Подозрительно большое значение ${type}: ${result}. Возможно, требуется корректировка парсинга.`);
      // Не конвертируем автоматически, так как новый парсер должен извлекать правильные значения
    }
  }
  
  console.log(`✅ ${type}: "${text}" -> ${result}`);
  return result;
}

// Альтернативный поиск милей
function findMilesAlternative(element) {
  const text = element.textContent || '';
  
  // Ищем паттерны миль
  const milesPatterns = [
    /(\d+(?:,\d+)*)\s*(?:mi|miles|миль|мил)/gi,
    /(?:miles|миль|мил):\s*(\d+(?:,\d+)*)/gi,
    /(?:distance|расстояние):\s*(\d+(?:,\d+)*)/gi
  ];
  
  for (const pattern of milesPatterns) {
    const match = text.match(pattern);
    if (match) {
      const number = parseNumberImproved(match[0], 'miles');
      if (number > 0 && number < 10000) {
        return number;
      }
    }
  }
  
  return 0;
}

// Альтернативный поиск ставки
function findRateAlternative(element) {
  const text = element.textContent || '';
  
  // Ищем паттерны ставок
  const ratePatterns = [
    /\$(\d+(?:,\d+)*(?:\.\d{2})?)/g,
    /(?:rate|ставка|цена):\s*\$?(\d+(?:,\d+)*(?:\.\d{2})?)/gi,
    /(?:pay|оплата):\s*\$?(\d+(?:,\d+)*(?:\.\d{2})?)/gi
  ];
  
  const numbers = [];
  
  for (const pattern of ratePatterns) {
    let match;
    while ((match = pattern.exec(text)) !== null) {
      const number = parseNumberImproved(match[1], 'rate');
      if (number > 100 && number < 100000) { // Разумные границы для ставки
        numbers.push(number);
      }
    }
  }
  
  // Возвращаем самую большую найденную ставку (скорее всего общая ставка)
  return numbers.length > 0 ? Math.max(...numbers) : 0;
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

// Расчет приоритета груза
function calculatePriority(loadData, profitability) {
  if (!profitability.isProfitable) {
    return 'LOW';
  }
  
  let score = 0;
  
  // Базовый балл за ставку за милю
  if (profitability.ratePerMile >= 4.0) score += 30;
  else if (profitability.ratePerMile >= 3.0) score += 20;
  else if (profitability.ratePerMile >= 2.5) score += 10;
  
  // Балл за короткий deadhead
  if (loadData.deadhead <= 10) score += 20;
  else if (loadData.deadhead <= 25) score += 15;
  else if (loadData.deadhead <= 50) score += 10;
  
  // Балл за хорошее расстояние
  if (loadData.miles >= 300 && loadData.miles <= 800) score += 15;
  else if (loadData.miles >= 200) score += 10;
  
  // Балл за общую прибыльность
  if (profitability.totalRevenue >= 2000) score += 15;
  else if (profitability.totalRevenue >= 1000) score += 10;
  
  // Определяем приоритет по общему баллу
  if (score >= 60) return 'HIGH';
  if (score >= 30) return 'MEDIUM';
  return 'LOW';
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
  
  // Фильтр по регионам (улучшенная версия)
  if (settings.regions && settings.regions.length > 0) {
    const matchesRegion = settings.regions.some(region => {
      const regionLower = region.trim().toLowerCase();
      
      // Пустые значения пропускаем
      if (!regionLower) return false;
      
      // Проверяем точное совпадение штатов (сокращения)
      if (regionLower.length === 2) {
        const regionUpper = regionLower.toUpperCase();
        // Проверяем в тексте pickup и delivery
        if ((load.pickup && load.pickup.includes(regionUpper)) || 
            (load.delivery && load.delivery.includes(regionUpper))) {
          return true;
        }
      }
      
      // Проверяем вхождение в названия городов/локаций
      const pickupMatch = load.pickup && load.pickup.toLowerCase().includes(regionLower);
      const deliveryMatch = load.delivery && load.delivery.toLowerCase().includes(regionLower);
      
      return pickupMatch || deliveryMatch;
    });
    
    if (!matchesRegion) {
      console.log('🚫 Load filtered out by region:', JSON.stringify({ 
        loadRegions: {
          pickup: load.pickup,
          delivery: load.delivery
        },
        filterRegions: settings.regions
      }, null, 2));
      return false;
    } else {
      console.log('✅ Load matches region filter:', JSON.stringify({
        loadRegions: {
          pickup: load.pickup,
          delivery: load.delivery
        },
        filterRegions: settings.regions
      }, null, 2));
    }
  }
  
  return true;
}

// Адаптивная настройка интервала сканирования (оптимизированная версия)
function adjustScanInterval(result) {
  const currentInterval = monitoringState.adaptiveInterval;
  const baseInterval = (monitoringState.settings && monitoringState.settings.scanInterval) || 3000;
  let newInterval = currentInterval;
  
  switch (result) {
    case 'profitable_found':
      // Найдены прибыльные грузы - максимально ускоряем
      newInterval = Math.max(1500, currentInterval - 1000);
      break;
      
    case 'loads_found':
      // Найдены новые грузы - ускоряем сканирование
      newInterval = Math.max(2000, currentInterval - 500);
      break;
      
    case 'no_new_loads':
      // Новых грузов нет - замедляем сканирование
      newInterval = Math.min(baseInterval * 2, currentInterval + 1000);
      break;
      
    case 'no_loads':
      // Грузов вообще нет на странице - значительно замедляем
      newInterval = Math.min(baseInterval * 3, currentInterval + 2000);
      break;
      
    case 'error':
      // Ошибка сканирования - замедляем для снижения нагрузки
      newInterval = Math.min(baseInterval * 2.5, currentInterval + 1500);
      break;
      
    case 'slow_scan':
      // Медленное сканирование - увеличиваем интервал
      newInterval = Math.min(baseInterval * 2, currentInterval + 1000);
      break;
      
    default:
      // Возвращаем к базовому интервалу
      newInterval = baseInterval;
  }
  
  // Ограничиваем диапазон интервалов
  newInterval = Math.max(1500, Math.min(15000, newInterval));
  
  if (newInterval !== currentInterval) {
    console.log(`Scan interval adjusted: ${currentInterval}ms -> ${newInterval}ms (reason: ${result})`);
    monitoringState.adaptiveInterval = newInterval;
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
  
  // Очищаем throttle кеш от старых записей
  for (const [key, timestamp] of logThrottle.entries()) {
    if (now - timestamp > maxAge) {
      logThrottle.delete(key);
    }
  }
  
  console.log(`Cache cleaned. Remaining loads: ${monitoringState.foundLoads.size}, throttle entries: ${logThrottle.size}`);
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

// Функция проверки валидности контекста расширения
function isExtensionContextValid() {
  try {
    chrome.runtime.id;
    return true;
  } catch (error) {
    console.warn('⚠️ Extension context invalidated:', error.message);
    return false;
  }
}

// Ограничение частоты логирования
const logThrottle = new Map();

function throttledLog(key, logFunction, message, interval = 30000) {
  const now = Date.now();
  const lastLog = logThrottle.get(key);
  
  if (!lastLog || now - lastLog > interval) {
    logThrottle.set(key, now);
    logFunction(message);
  }
}

// Безопасная отправка сообщений в background script
async function safeSendMessage(message, retries = 3) {
  for (let i = 0; i < retries; i++) {
    try {
      if (!isExtensionContextValid()) {
        throttledLog('context_invalid', console.warn, '❌ Extension context invalid, skipping message send');
        return null;
      }
      
      const response = await chrome.runtime.sendMessage(message);
      return response;
    } catch (error) {
              throttledLog(`message_fail_${i}`, console.warn, `⚠️ Message send attempt ${i + 1} failed: ${error.message}`);
      
      if (error.message.includes('Extension context invalidated') || 
          error.message.includes('receiving end does not exist')) {
        // Контекст инвалидирован, дальнейшие попытки бесполезны
        console.error('❌ Extension context permanently invalidated');
        return null;
      }
      
      if (i === retries - 1) {
        console.error('❌ All message send attempts failed:', error);
        return null;
      }
      
      // Ждем перед повторной попыткой
      await new Promise(resolve => setTimeout(resolve, 500 * (i + 1)));
    }
  }
  return null;
}

// Функция автоматического запуска мониторинга
async function startAutomaticMonitoring() {
  try {
    console.log('🤖 Запуск автоматического мониторинга...');
    
    // Проверяем валидность контекста расширения
    if (!isExtensionContextValid()) {
      console.error('❌ Extension context invalidated, cannot start monitoring');
      return;
    }
    
    // Убеждаемся что у нас есть настройки по умолчанию
    if (!monitoringState.settings) {
      monitoringState.settings = {
        minRatePerMile: 2.5,
        maxDeadhead: 50,
        scanInterval: 3000,
        soundAlerts: true
      };
    }
    
    // Получаем настройки из storage с обработкой ошибок
    try {
      const response = await safeSendMessage({ type: 'GET_SETTINGS' });
      if (response && response.success && response.settings) {
        // Объединяем полученные настройки с настройками по умолчанию
        monitoringState.settings = {
          ...monitoringState.settings,
          ...response.settings
        };
        console.log('✅ Настройки успешно загружены:', monitoringState.settings);
      } else {
        console.warn('⚠️ Не удалось получить настройки, используем значения по умолчанию');
      }
    } catch (messageError) {
      console.warn('⚠️ Ошибка при получении настроек:', messageError);
    }
    
    // Запускаем мониторинг
    monitoringState.isActive = true;
    monitoringState.adaptiveInterval = (monitoringState.settings && monitoringState.settings.scanInterval) || 3000;
    monitoringState.lastScanTime = Date.now();
    
    // Показываем индикатор мониторинга
    showMonitoringIndicator();
    
    // Запускаем watchdog
    startMonitoringWatchdog();
    
    // Уведомляем background script с безопасной отправкой
    safeSendMessage({
      type: 'MONITORING_STATUS',
      data: {
        isActive: true,
        isLoggedIn: true,
        timestamp: Date.now()
      }
    }).catch(err => console.warn('Не удалось уведомить background script:', err));
    
    // Начинаем первое сканирование через небольшую задержку
    setTimeout(() => {
      if (monitoringState.isActive) {
        console.log('🎯 Запускаем первое сканирование...');
        performScan();
      }
    }, 2000);
    
    console.log('✅ Автоматический мониторинг успешно запущен');
    
  } catch (error) {
    console.error('❌ Ошибка при автоматическом запуске мониторинга:', error);
    
    // Пытаемся уведомить об ошибке
    safeSendMessage({
      type: 'MONITORING_ERROR',
      data: {
        error: error.message,
        timestamp: Date.now()
      }
    });
  }
}

// Добавляем команду для запуска диагностики через консоль
window.freightDiag = diagnosePage;
console.log('💡 Tip: Run "freightDiag()" in console to diagnose page structure');
console.log('💡 Tip: Run "testLothianCardParsing()" in console to test LOTHIAN parsing');

console.log('🔥 FreightPower Load Monitor content script инициализирован - автоматическое сканирование активно!');

// Новая функция для парсинга груза из текстовой строки
function parseLoadFromText(text) {
  console.log('📄 Парсинг груза из текста:', text);
  
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
    weight: null
  };
  
  // 1. ID - первое длинное число (обычно 10 цифр)
  const idMatch = text.match(/\b(\d{10})\b/);
  if (idMatch) {
    loadData.id = idMatch[1];
  }
  
  // 2. Capacity Type - ищем известные типы
  const capacityTypes = ['Power Only', 'Dry Van', 'Flatbed', 'Reefer', 'Van'];
  for (const type of capacityTypes) {
    // Используем регулярное выражение для поиска типа даже если текст слит
    const typeRegex = new RegExp(type.replace(' ', '\\s*'), 'i');
    if (typeRegex.test(text)) {
      loadData.capacityType = type;
      break;
    }
  }
  
  // 3. Rate - первое число после $ (например, $704 из "$704388 miles")
  const rateMatch = text.match(/\$\s*(\d{1,6})/);
  if (rateMatch) {
    loadData.rate = parseFloat(rateMatch[1]);
  }
  
  // 4. Miles - число перед словом "miles"
  const milesMatch = text.match(/(\d+)\s*miles/i);
  if (milesMatch) {
    loadData.miles = parseInt(milesMatch[1]);
  }
  
  // 5. Weight - число перед "lbs"
  const weightMatch = text.match(/([\d,]+)\s*lbs/i);
  if (weightMatch) {
    loadData.weight = weightMatch[1].replace(/,/g, '');
  }
  
  // 6. Deadhead - ТОЛЬКО из строки "Deadhead XX mi"
  const deadheadMatch = text.match(/Deadhead\s+(\d+)\s*mi/i);
  if (deadheadMatch) {
    loadData.deadhead = parseInt(deadheadMatch[1]);
  }
  
  // 7. Locations - формат "ГОРОД, ШТАТ" (например, "WILMER, TX")
  const locationPattern = /\b([A-Z][A-Z\s]+),\s*([A-Z]{2})\b/g;
  const locations = [];
  let match;
  while ((match = locationPattern.exec(text)) !== null) {
    locations.push(`${match[1].trim()}, ${match[2]}`);
  }
  
  // Первая локация после capacity type - pickup, вторая - delivery
  if (locations.length >= 2) {
    loadData.pickup = locations[0];
    loadData.delivery = locations[1];
  }
  
  // 8. Даты - ищем формат "Aug 25" или "Aug 25 6:00am"
  const datePattern = /\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}\b/g;
  const dates = [];
  while ((match = datePattern.exec(text)) !== null) {
    dates.push(match[0]);
  }
  
  if (dates.length >= 2) {
    loadData.pickupDate = dates[0];
    loadData.deliveryDate = dates[1];
  }
  
  // Рассчитываем rate per mile
  if (loadData.rate > 0 && loadData.miles > 0) {
    loadData.ratePerMile = (loadData.rate / loadData.miles).toFixed(2);
  }
  
  console.log('✅ Распарсенные данные:', loadData);
  return loadData;
}

// Функция для тестирования парсера
function testLoadParser() {
  console.log('🧪 Тестирование парсера грузов...');
  
  const testCases = [
    "4007568740 Power Only $704 388 miles 24,710 lbs WILMER, TX Aug 25 6:00am - 11:59pm Deadhead 16 mi GODDARD, KS Aug 26 9:00am - 9:00am",
    "4007566104Dry Van$761413 miles10,000 lbsDESOTO, TXAug 25 1:00pm - 2:00pmLive LoadDeadhead 17 miJACKSON, MS"
  ];
  
  console.log('📋 Тестовые случаи:');
  testCases.forEach((testCase, index) => {
    console.log(`\n--- Тест ${index + 1} ---`);
    console.log('Входные данные:', testCase);
    
    const result = parseLoadFromText(testCase);
    console.log('Результат парсинга:', result);
    
    // Проверка результатов
    const checks = {
      'ID найден': result.id !== null,
      'Тип оборудования': result.capacityType !== null,
      'Ставка корректная': result.rate > 0 && result.rate < 10000,
      'Мили найдены': result.miles > 0,
      'Откуда': result.pickup !== null,
      'Куда': result.delivery !== null,
      'Deadhead': result.deadhead >= 0,
      'Rate per mile': result.ratePerMile > 0
    };
    
    console.log('Проверки:');
    Object.entries(checks).forEach(([check, passed]) => {
      console.log(`  ${passed ? '✅' : '❌'} ${check}: ${passed ? 'Да' : 'Нет'}`);
    });
  });
  
  console.log('\n✅ Тестирование завершено');
}

window.testLoadParser = testLoadParser;

