// FreightPower Load Monitor - Background Service Worker

// Состояние расширения
let monitoringState = {
  isActive: false,
  tabId: null,
  sessionId: null,
  lastCheck: null,
  totalLoadsFound: 0,
  profitableLoads: 0
};

// Настройки по умолчанию
const DEFAULT_SETTINGS = {
  minRatePerMile: 2.50,
  maxDeadhead: 50,
  minDistance: 200,
  maxDistance: null, // Без ограничений
  equipmentTypes: ['Dry Van', 'Reefer', 'Flatbed'],
  regions: [],
  soundAlerts: true,
  notificationFrequency: 'all', // all, high_priority, none
  scanInterval: 3000 // 3 секунды
};

// Инициализация при запуске расширения
chrome.runtime.onStartup.addListener(async () => {
  await initializeExtension();
});

chrome.runtime.onInstalled.addListener(async (details) => {
  await initializeExtension();
  
  // Создаем контекстное меню только если API доступен
  if (chrome.contextMenus) {
    try {
      // Сначала удаляем существующие меню
      await chrome.contextMenus.removeAll();
      
      // Создаем новое меню
      chrome.contextMenus.create({
        id: "toggle-monitoring",
        title: "Toggle FreightPower Monitoring",
        contexts: ["page"],
        documentUrlPatterns: ["https://freightpower.schneider.com/*"]
      }, () => {
        // Проверяем на ошибки
        if (chrome.runtime.lastError) {
          console.error('Error creating context menu:', chrome.runtime.lastError);
        } else {
          console.log('Context menu created successfully');
        }
      });
    } catch (error) {
      console.error('Error with context menus:', error);
    }
  }
});

// Инициализация настроек
async function initializeExtension() {
  try {
    const result = await chrome.storage.sync.get(['settings', 'statistics']);
    
    if (!result.settings) {
      await chrome.storage.sync.set({ settings: DEFAULT_SETTINGS });
    }
    
    if (!result.statistics) {
      await chrome.storage.sync.set({ 
        statistics: {
          totalScans: 0,
          loadsFound: 0,
          profitableLoads: 0,
          lastActive: null,
          sessionsCount: 0
        }
      });
    }
    
    console.log('FreightPower Monitor initialized');
  } catch (error) {
    console.error('Error initializing extension:', error);
  }
}

// Отслеживание активности вкладок
chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  if (changeInfo.status === 'complete' && tab.url && 
      tab.url.includes('freightpower.schneider.com')) {
    
    console.log('FreightPower tab detected:', tab.url);
    
    // Убеждаемся, что content script загружен
    try {
      // Проверяем, загружен ли уже content script
      const [result] = await chrome.scripting.executeScript({
        target: { tabId: tabId },
        func: () => {
          return typeof window.freightDiag !== 'undefined';
        }
      });
      
      if (!result.result) {
        console.log('Content script not loaded, injecting...');
        // Инжектим content script если он еще не загружен
        await chrome.scripting.executeScript({
          target: { tabId: tabId },
          files: ['content.js']
        });
      }
      
      // Устанавливаем tabId для мониторинга
      monitoringState.tabId = tabId;
      monitoringState.sessionId = generateSessionId();
      
      console.log('Content script ready on tab:', tabId);
      
    } catch (error) {
      console.error('Error checking/injecting content script:', error);
    }
  }
});

// Обработка сообщений от content script (улучшенная версия)
chrome.runtime.onMessage.addListener(async (message, sender, sendResponse) => {
  const startTime = Date.now();
  
  try {
    // Валидация базовой структуры сообщения
    if (!message || !message.type) {
      throw new Error('Invalid message format: missing type');
    }
    
    // Валидация отправителя
    if (!sender || !sender.tab || !sender.tab.id) {
      console.warn('Message received without valid sender information');
    }
    
    console.log(`Handling message: ${message.type} from tab ${sender?.tab?.id}`);
    
    switch (message.type) {
      case 'LOGIN_DETECTED':
        if (!sender?.tab?.id) {
          throw new Error('LOGIN_DETECTED: No tab ID provided');
        }
        await handleLoginDetected(sender.tab.id);
        sendResponse({ success: true, timestamp: Date.now() });
        break;
        
      case 'LOGOUT_DETECTED':
        await handleLogoutDetected();
        sendResponse({ success: true, timestamp: Date.now() });
        break;
        
      case 'LOAD_FOUND':
        if (!message.data) {
          throw new Error('LOAD_FOUND: No load data provided');
        }
        await handleLoadFound(message.data);
        sendResponse({ success: true, timestamp: Date.now() });
        break;
        
      case 'MONITORING_STATUS':
        const status = {
          success: true,
          isActive: monitoringState.isActive,
          isLoggedIn: monitoringState.isLoggedIn,
          tabId: monitoringState.tabId,
          sessionId: monitoringState.sessionId,
          totalLoadsFound: monitoringState.totalLoadsFound,
          profitableLoads: monitoringState.profitableLoads,
          timestamp: Date.now()
        };
        sendResponse(status);
        break;
        
      case 'UPDATE_STATISTICS':
        if (!message.data || typeof message.data !== 'object') {
          throw new Error('UPDATE_STATISTICS: Invalid statistics data');
        }
        await updateStatistics(message.data);
        sendResponse({ success: true, timestamp: Date.now() });
        break;
        
      case 'GET_SETTINGS':
        try {
          const settings = await getSettings();
          sendResponse({ success: true, settings, timestamp: Date.now() });
        } catch (settingsError) {
          console.error('Error getting settings:', settingsError);
          sendResponse({ 
            success: false, 
            error: 'Failed to get settings', 
            details: settingsError.message,
            timestamp: Date.now()
          });
        }
        break;
        
      default:
        console.warn('Unknown message type:', message.type);
        sendResponse({ 
          success: false, 
          error: `Unknown message type: ${message.type}`,
          timestamp: Date.now()
        });
    }
    
    const processingTime = Date.now() - startTime;
    if (processingTime > 1000) {
      console.warn(`Slow message processing: ${message.type} took ${processingTime}ms`);
    }
    
  } catch (error) {
    const processingTime = Date.now() - startTime;
    console.error(`Error handling message ${message?.type}:`, {
      error: error.message,
      stack: error.stack,
      processingTime,
      messageType: message?.type,
      tabId: sender?.tab?.id
    });
    
    sendResponse({ 
      success: false, 
      error: error.message,
      messageType: message?.type,
      timestamp: Date.now(),
      processingTime
    });
  }
  
  return true; // Указывает, что ответ будет асинхронным
});

// Обработка обнаружения авторизации (улучшенная версия)
async function handleLoginDetected(tabId) {
  try {
    console.log('Login detected, starting monitoring...', { tabId });
    
    // Валидация табId
    if (!tabId || typeof tabId !== 'number') {
      throw new Error(`Invalid tabId: ${tabId}`);
    }
    
    // Проверяем, что вкладка еще существует
    try {
      await chrome.tabs.get(tabId);
    } catch (tabError) {
      throw new Error(`Tab ${tabId} no longer exists: ${tabError.message}`);
    }
    
    monitoringState.isActive = true;
    monitoringState.isLoggedIn = true;
    monitoringState.tabId = tabId;
    monitoringState.lastCheck = Date.now();
    
    // Обновляем иконку расширения
    await updateExtensionIcon('active');
    
    // Отправляем команду на запуск мониторинга с retry логикой
    let retryCount = 0;
    const maxRetries = 3;
    
    while (retryCount < maxRetries) {
      try {
        const settings = await getSettings();
        await chrome.tabs.sendMessage(tabId, {
          type: 'START_MONITORING',
          settings: settings
        });
        
        console.log('Monitoring started successfully on tab', tabId);
        break;
        
      } catch (error) {
        retryCount++;
        console.warn(`Failed to start monitoring (attempt ${retryCount}):`, error.message);
        
        if (retryCount >= maxRetries) {
          throw new Error(`Failed to start monitoring after ${maxRetries} attempts: ${error.message}`);
        }
        
        // Ждем перед повторной попыткой
        await new Promise(resolve => setTimeout(resolve, 1000 * retryCount));
      }
    }
    
    // Обновляем статистику
    await updateStatistics({ sessionsCount: 1 });
    
  } catch (error) {
    console.error('Error in handleLoginDetected:', error);
    
    // Сбрасываем состояние при ошибке
    monitoringState.isActive = false;
    monitoringState.isLoggedIn = false;
    await updateExtensionIcon('inactive');
    
    throw error;
  }
}

// Обработка выхода из системы
async function handleLogoutDetected() {
  console.log('Logout detected, stopping monitoring...');
  
  monitoringState.isActive = false;
  monitoringState.tabId = null;
  
  await updateExtensionIcon('inactive');
}

// Обработка найденного груза (улучшенная версия)
async function handleLoadFound(loadData) {
  try {
    console.log('Load found:', loadData);
    
    // Валидация данных груза
    if (!loadData || typeof loadData !== 'object') {
      throw new Error('Invalid load data format');
    }
    
    // Проверяем обязательные поля
    const requiredFields = ['id', 'pickup', 'delivery'];
    for (const field of requiredFields) {
      if (!loadData[field]) {
        console.warn(`Missing required field: ${field} in load data`);
      }
    }
    
    monitoringState.totalLoadsFound++;
    
    if (loadData.isProfitable) {
      // Сохраняем только прибыльные грузы в список последних найденных
      try {
        await saveRecentLoad(loadData);
        monitoringState.profitableLoads++;
        
        const settings = await getSettings();
        
        // Отправляем уведомление
        if (settings.notificationFrequency !== 'none' && 
            (settings.notificationFrequency === 'all' || loadData.priority === 'HIGH')) {
          
          try {
            await showNotification(loadData);
          } catch (notificationError) {
            console.error('Failed to show notification:', notificationError);
          }
        }
        
        // Воспроизводим звук для HIGH priority грузов
        if (settings.soundAlerts && loadData.priority === 'HIGH') {
          try {
            await playAlertSound();
          } catch (soundError) {
            console.error('Failed to play alert sound:', soundError);
          }
        }
        
        // Отправляем сообщение в popup если он открыт
        try {
          await chrome.runtime.sendMessage({
            type: 'LOAD_FOUND',
            data: loadData
          });
        } catch (popupError) {
          console.log('Popup not open, load saved to storage');
        }
        
      } catch (saveError) {
        console.error('Failed to save load data:', saveError);
        // Продолжаем выполнение даже если сохранение не удалось
      }
    }
    
    // Обновляем статистику
    try {
      await updateStatistics({
        totalScans: 1,
        loadsFound: 1,
        profitableLoads: loadData.isProfitable ? 1 : 0,
        lastActive: Date.now()
      });
    } catch (statsError) {
      console.error('Failed to update statistics:', statsError);
    }
    
  } catch (error) {
    console.error('Error in handleLoadFound:', error);
    throw error;
  }
}

// Показ уведомления
async function showNotification(loadData) {
  const notificationId = `load-${loadData.id}-${Date.now()}`;
  
  await chrome.notifications.create(notificationId, {
    type: 'basic',
    iconUrl: 'icons/icon48.png',
    title: `💰 Прибыльный груз найден! (${loadData.priority})`,
    message: `${loadData.pickup} → ${loadData.delivery}\n` +
             `$${loadData.ratePerMile.toFixed(2)}/миля | ${loadData.miles} миль | DH: ${loadData.deadhead}`,
    priority: loadData.priority === 'HIGH' ? 2 : 1,
    requireInteraction: loadData.priority === 'HIGH'
  });
  
  // Автоматически закрываем уведомление через 10 секунд для MEDIUM priority
  if (loadData.priority !== 'HIGH') {
    setTimeout(() => {
      chrome.notifications.clear(notificationId);
    }, 10000);
  }
}

// Воспроизведение звукового сигнала
async function playAlertSound() {
  if (monitoringState.tabId) {
    try {
      await chrome.tabs.sendMessage(monitoringState.tabId, {
        type: 'PLAY_SOUND'
      });
    } catch (error) {
      console.error('Error playing sound:', error);
    }
  }
}

// Обновление иконки расширения
async function updateExtensionIcon(status) {
  const iconPath = status === 'active' ? 'icon-active' : 'icon';
  
  try {
    // Используем существующие иконки, так как у нас нет отдельных активных иконок
    await chrome.action.setIcon({
      path: {
        16: `icons/icon16.png`,
        32: `icons/icon32.png`,
        48: `icons/icon48.png`,
        128: `icons/icon128.png`
      }
    });
    
    // Показываем количество найденных грузов на бэйдже
    if (status === 'active') {
      await chrome.action.setBadgeText({
        text: monitoringState.profitableLoads > 0 ? 
              monitoringState.profitableLoads.toString() : ''
      });
      
      await chrome.action.setBadgeBackgroundColor({
        color: '#4CAF50'
      });
    } else {
      await chrome.action.setBadgeText({ text: '' });
    }
    
  } catch (error) {
    console.error('Error updating icon:', error);
  }
}

// Получение настроек
async function getSettings() {
  try {
    const result = await chrome.storage.sync.get('settings');
    return result.settings || DEFAULT_SETTINGS;
  } catch (error) {
    console.error('Error getting settings:', error);
    return DEFAULT_SETTINGS;
  }
}

// Обновление статистики
async function updateStatistics(data) {
  try {
    const result = await chrome.storage.sync.get('statistics');
    const stats = result.statistics || {};
    
    // Инкрементальное обновление
    Object.keys(data).forEach(key => {
      if (typeof data[key] === 'number' && key !== 'lastActive') {
        stats[key] = (stats[key] || 0) + data[key];
      } else {
        stats[key] = data[key];
      }
    });
    
    await chrome.storage.sync.set({ statistics: stats });
  } catch (error) {
    console.error('Error updating statistics:', error);
  }
}

// Генерация ID сессии
function generateSessionId() {
  return `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
}

// Обработка клика по контекстному меню
if (chrome.contextMenus) {
  chrome.contextMenus.onClicked.addListener(async (info, tab) => {
    if (info.menuItemId === "toggle-monitoring" && tab && tab.id) {
      try {
        if (monitoringState.isActive) {
          await chrome.tabs.sendMessage(tab.id, { type: 'STOP_MONITORING' });
          monitoringState.isActive = false;
          await updateExtensionIcon('inactive');
        } else {
          await chrome.tabs.sendMessage(tab.id, { 
            type: 'START_MONITORING',
            settings: await getSettings()
          });
          monitoringState.isActive = true;
          monitoringState.tabId = tab.id;
          await updateExtensionIcon('active');
        }
      } catch (error) {
        console.error('Error toggling monitoring:', error);
      }
    }
  });
}

// Обработка закрытия вкладки
chrome.tabs.onRemoved.addListener((tabId) => {
  if (tabId === monitoringState.tabId) {
    monitoringState.isActive = false;
    monitoringState.tabId = null;
    updateExtensionIcon('inactive');
  }
});

// Периодическая проверка состояния
setInterval(async () => {
  if (monitoringState.isActive && monitoringState.tabId) {
    try {
      // Проверяем, что вкладка еще существует
      await chrome.tabs.get(monitoringState.tabId);
    } catch (error) {
      // Вкладка закрыта
      monitoringState.isActive = false;
      monitoringState.tabId = null;
      await updateExtensionIcon('inactive');
    }
  }
}, 30000); // Проверяем каждые 30 секунд

// Сохранение найденного груза в список последних
async function saveRecentLoad(loadData) {
  try {
    // Получаем существующий список
    const result = await chrome.storage.local.get('recentLoads');
    let recentLoads = result.recentLoads || [];
    
    // Создаем новый груз с уникальным ID
    let loadId = loadData.id;
    
    // Фильтруем некорректные ID
    if (loadId && (
      loadId.toLowerCase().includes('dlefield') ||
      loadId.toLowerCase().includes('field') ||
      loadId.toLowerCase().includes('placeholder') ||
      loadId.length < 3 ||
      loadId.length > 50
    )) {
      loadId = null;
    }
    
    const newLoad = {
      ...loadData,
      foundAt: Date.now(),
      id: loadId || `load-${Date.now()}`
    };
    
    // Проверяем на дубликаты (по ID и основным параметрам)
    const isDuplicate = recentLoads.some(existingLoad => {
      // Проверяем точное совпадение ID
      if (existingLoad.id === newLoad.id) return true;
      
      // Проверяем совпадение основных параметров (маршрут, мили, ставка)
      return existingLoad.pickup === newLoad.pickup &&
             existingLoad.delivery === newLoad.delivery &&
             existingLoad.miles === newLoad.miles &&
             existingLoad.ratePerMile === newLoad.ratePerMile &&
             Math.abs(existingLoad.foundAt - newLoad.foundAt) < 60000; // в течение 1 минуты
    });
    
    if (isDuplicate) {
      console.log('Duplicate load detected, skipping save:', newLoad.id);
      return;
    }
    
    // Добавляем новый груз в начало списка
    recentLoads.unshift(newLoad);
    
    // Ограничиваем список 20 элементами
    if (recentLoads.length > 20) {
      recentLoads = recentLoads.slice(0, 20);
    }
    
    // Сохраняем обновленный список
    await chrome.storage.local.set({ recentLoads });
    
    console.log(`Saved load to recent list. Total: ${recentLoads.length}`);
  } catch (error) {
    console.error('Error saving recent load:', error);
  }
}

console.log('FreightPower Load Monitor background script loaded');
