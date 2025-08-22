// Service Worker для управления мониторингом
let monitoringTabs = new Set();
let notificationId = 0;

// Обработка установки расширения
chrome.runtime.onInstalled.addListener(() => {
  console.log('FreightPower Monitor установлен');
  chrome.storage.local.set({
    isMonitoring: false,
    settings: {
      minRatePerMile: 2.50,
      maxDeadhead: 50,
      minDistance: 200,
      maxDistance: null,
      equipmentTypes: ['Dry Van', 'Reefer', 'Flatbed'],
      scanInterval: 3000,
      enableNotifications: true,
      enableSound: true
    },
    statistics: {
      totalLoadsFound: 0,
      profitableLoadsFound: 0,
      lastScanTime: null,
      monitoringStartTime: null
    }
  });
});

// Обработка сообщений от content script
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  switch (message.type) {
    case 'START_MONITORING':
      startMonitoring(sender.tab.id);
      break;
      
    case 'STOP_MONITORING':
      stopMonitoring(sender.tab.id);
      break;
      
    case 'LOAD_FOUND':
      handleLoadFound(message.load, sender.tab.id);
      break;
      
    case 'LOGIN_DETECTED':
      handleLoginDetected(sender.tab.id);
      break;
      
    case 'LOGOUT_DETECTED':
      handleLogoutDetected(sender.tab.id);
      break;
      
    case 'GET_STATUS':
      sendResponse({
        isMonitoring: monitoringTabs.has(sender.tab.id),
        statistics: getStatistics()
      });
      break;
  }
});

// Обработка закрытия вкладок
chrome.tabs.onRemoved.addListener((tabId) => {
  if (monitoringTabs.has(tabId)) {
    monitoringTabs.delete(tabId);
    updateBadge();
  }
});

// Обработка обновления вкладок
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === 'complete' && 
      tab.url && 
      tab.url.includes('freightpower.schneider.com')) {
    // Автоматически запускаем мониторинг при загрузке FreightPower
    setTimeout(() => {
      chrome.tabs.sendMessage(tabId, { type: 'CHECK_LOGIN_STATUS' });
    }, 2000);
  }
});

function startMonitoring(tabId) {
  monitoringTabs.add(tabId);
  updateBadge();
  
  chrome.storage.local.get(['statistics'], (result) => {
    const stats = result.statistics || {};
    stats.monitoringStartTime = Date.now();
    chrome.storage.local.set({ 
      isMonitoring: true,
      statistics: stats 
    });
  });
  
  console.log(`Мониторинг запущен для вкладки ${tabId}`);
}

function stopMonitoring(tabId) {
  monitoringTabs.delete(tabId);
  updateBadge();
  
  if (monitoringTabs.size === 0) {
    chrome.storage.local.set({ isMonitoring: false });
  }
  
  console.log(`Мониторинг остановлен для вкладки ${tabId}`);
}

function handleLoadFound(load, tabId) {
  chrome.storage.local.get(['statistics', 'settings'], (result) => {
    const stats = result.statistics || {};
    const settings = result.settings || {};
    
    stats.totalLoadsFound++;
    stats.lastScanTime = Date.now();
    
    if (load.profitability.isProfitable) {
      stats.profitableLoadsFound++;
      
      // Показываем уведомление для прибыльных грузов
      if (settings.enableNotifications) {
        showLoadNotification(load);
      }
      
      // Звуковой сигнал для HIGH priority грузов
      if (settings.enableSound && load.profitability.priority === 'HIGH') {
        playNotificationSound();
      }
    }
    
    chrome.storage.local.set({ statistics: stats });
  });
}

function handleLoginDetected(tabId) {
  console.log(`Авторизация обнаружена на вкладке ${tabId}`);
  startMonitoring(tabId);
}

function handleLogoutDetected(tabId) {
  console.log(`Выход обнаружен на вкладке ${tabId}`);
  stopMonitoring(tabId);
}

function showLoadNotification(load) {
  const notificationId = `load_${Date.now()}`;
  
  chrome.notifications.create(notificationId, {
    type: 'basic',
    iconUrl: 'icons/icon48.png',
    title: `Найден прибыльный груз!`,
    message: `${load.loadId} - ${load.pickupLocation} → ${load.deliveryLocation}\nСтавка: $${load.rate}/милю`,
    priority: load.profitability.priority === 'HIGH' ? 2 : 1
  });
  
  // Автоматически закрываем уведомление через 10 секунд
  setTimeout(() => {
    chrome.notifications.clear(notificationId);
  }, 10000);
}

function playNotificationSound() {
  // Создаем простой звуковой сигнал
  const audio = new Audio('data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoGAACBhYqFbF1fdJivrJBhNjVgodDbq2EcBj+a2/LDciUFLIHO8tiJNwgZaLvt559NEAxQp+PwtmMcBjiR1/LMeSwFJHfH8N2QQAoUXrTp66hVFApGn+DyvmwhBSuBzvLZiTYIG2m98OScTgwOUarm7blmGgU7k9n1unEiBC13yO/eizEIHWq+8+OWT');
  audio.play().catch(() => {
    // Игнорируем ошибки воспроизведения
  });
}

function updateBadge() {
  const count = monitoringTabs.size;
  if (count > 0) {
    chrome.action.setBadgeText({ text: count.toString() });
    chrome.action.setBadgeBackgroundColor({ color: '#4CAF50' });
  } else {
    chrome.action.setBadgeText({ text: '' });
  }
}

function getStatistics() {
  return new Promise((resolve) => {
    chrome.storage.local.get(['statistics'], (result) => {
      resolve(result.statistics || {});
    });
  });
}

// Обработка клика по уведомлению
chrome.notifications.onClicked.addListener((notificationId) => {
  // Открываем вкладку с FreightPower при клике на уведомление
  chrome.tabs.query({ url: 'https://freightpower.schneider.com/*' }, (tabs) => {
    if (tabs.length > 0) {
      chrome.tabs.update(tabs[0].id, { active: true });
    } else {
      chrome.tabs.create({ url: 'https://freightpower.schneider.com' });
    }
  });
});
