// FreightPower Load Monitor - Options Script

// Настройки по умолчанию
const DEFAULT_SETTINGS = {
  minRatePerMile: 2.50,
  maxDeadhead: 50,
  minDistance: 200,
  maxDistance: null,
  equipmentTypes: ['Dry Van', 'Reefer', 'Flatbed'],
  regions: [],
  notificationFrequency: 'all',
  soundAlerts: true,
  desktopNotifications: true,
  persistentNotifications: false,
  alertVolume: 70,
  scanInterval: 3000,
  adaptiveScanning: true,
  cacheTimeout: 30,
  debugMode: false,
  showIndicator: true
};

// Состояние приложения
let currentSettings = {};
let currentStatistics = {};
let activeTab = 'filters';
let hasUnsavedChanges = false;

// DOM элементы
const elements = {};

// Инициализация при загрузке
document.addEventListener('DOMContentLoaded', async () => {
  console.log('Options page loaded');
  
  initializeElements();
  setupEventListeners();
  await loadData();
  updateUI();
  
  // Автосохранение каждые 30 секунд если есть изменения
  setInterval(autoSave, 30000);
});

// Инициализация элементов DOM
function initializeElements() {
  // Навигация
  elements.navTabs = document.querySelectorAll('.nav-tab');
  elements.tabContents = document.querySelectorAll('.tab-content');
  
  // Фильтры
  elements.minRatePerMile = document.getElementById('minRatePerMile');
  elements.maxDeadhead = document.getElementById('maxDeadhead');
  elements.minDistance = document.getElementById('minDistance');
  elements.maxDistance = document.getElementById('maxDistance');
  elements.equipmentTypes = document.querySelectorAll('input[name="equipmentType"]');
  elements.regions = document.getElementById('regions');
  
  // Уведомления
  elements.notificationFrequency = document.getElementById('notificationFrequency');
  elements.soundAlerts = document.getElementById('soundAlerts');
  elements.desktopNotifications = document.getElementById('desktopNotifications');
  elements.persistentNotifications = document.getElementById('persistentNotifications');
  elements.alertVolume = document.getElementById('alertVolume');
  elements.testSound = document.getElementById('testSound');
  
  // Расширенные настройки
  elements.scanInterval = document.getElementById('scanInterval');
  elements.adaptiveScanning = document.getElementById('adaptiveScanning');
  elements.cacheTimeout = document.getElementById('cacheTimeout');
  elements.debugMode = document.getElementById('debugMode');
  elements.showIndicator = document.getElementById('showIndicator');
  
  // Статистика
  elements.totalScansCount = document.getElementById('totalScansCount');
  elements.totalLoadsCount = document.getElementById('totalLoadsCount');
  elements.profitableLoadsCount = document.getElementById('profitableLoadsCount');
  elements.successRate = document.getElementById('successRate');
  elements.sessionsTotal = document.getElementById('sessionsTotal');
  elements.lastActiveTime = document.getElementById('lastActiveTime');
  elements.avgScanInterval = document.getElementById('avgScanInterval');
  elements.memoryUsage = document.getElementById('memoryUsage');
  elements.activeCaches = document.getElementById('activeCaches');
  
  // Кнопки
  elements.saveSettings = document.getElementById('saveSettings');
  elements.resetToDefaults = document.getElementById('resetToDefaults');
  elements.saveStatus = document.getElementById('saveStatus');
  elements.exportSettings = document.getElementById('exportSettings');
  elements.importSettings = document.getElementById('importSettings');
  elements.resetSettings = document.getElementById('resetSettings');
  elements.clearData = document.getElementById('clearData');
  elements.exportStats = document.getElementById('exportStats');
  elements.resetStats = document.getElementById('resetStats');
  
  // Модальные окна
  elements.confirmModal = document.getElementById('confirmModal');
  elements.confirmTitle = document.getElementById('confirmTitle');
  elements.confirmMessage = document.getElementById('confirmMessage');
  elements.confirmOk = document.getElementById('confirmOk');
  elements.confirmCancel = document.getElementById('confirmCancel');
  elements.fileInput = document.getElementById('fileInput');
}

// Настройка обработчиков событий
function setupEventListeners() {
  // Навигация по вкладкам
  elements.navTabs.forEach(tab => {
    tab.addEventListener('click', () => switchTab(tab.dataset.tab));
  });
  
  // Отслеживание изменений в настройках
  const settingsInputs = [
    elements.minRatePerMile, elements.maxDeadhead, elements.minDistance, elements.maxDistance,
    elements.regions, elements.notificationFrequency, elements.soundAlerts,
    elements.desktopNotifications, elements.persistentNotifications, elements.alertVolume,
    elements.scanInterval, elements.adaptiveScanning, elements.cacheTimeout,
    elements.debugMode, elements.showIndicator
  ];
  
  settingsInputs.forEach(input => {
    if (input) {
      const eventType = input.type === 'checkbox' ? 'change' : 'input';
      input.addEventListener(eventType, () => {
        hasUnsavedChanges = true;
        updateSaveStatus('Есть несохраненные изменения', 'warning');
      });
    }
  });
  
  // Оборудование
  elements.equipmentTypes.forEach(checkbox => {
    checkbox.addEventListener('change', () => {
      hasUnsavedChanges = true;
      updateSaveStatus('Есть несохраненные изменения', 'warning');
    });
  });
  
  // Слайдер громкости
  if (elements.alertVolume) {
    elements.alertVolume.addEventListener('input', (e) => {
      const value = e.target.value;
      document.querySelector('.slider-value').textContent = `${value}%`;
      hasUnsavedChanges = true;
      updateSaveStatus('Есть несохраненные изменения', 'warning');
    });
  }
  
  // Кнопки
  elements.saveSettings?.addEventListener('click', saveSettings);
  elements.resetToDefaults?.addEventListener('click', () => showConfirmDialog(
    'Сброс к умолчаниям',
    'Все настройки будут сброшены к значениям по умолчанию. Продолжить?',
    resetToDefaults
  ));
  elements.testSound?.addEventListener('click', testSound);
  
  // Управление данными
  elements.exportSettings?.addEventListener('click', exportSettings);
  elements.importSettings?.addEventListener('click', () => elements.fileInput.click());
  elements.resetSettings?.addEventListener('click', () => showConfirmDialog(
    'Сброс настроек',
    'Все настройки будут удалены. Продолжить?',
    resetSettings
  ));
  elements.clearData?.addEventListener('click', () => showConfirmDialog(
    'Очистка всех данных',
    'Все данные расширения будут удалены безвозвратно. Продолжить?',
    clearAllData
  ));
  
  // Статистика
  elements.exportStats?.addEventListener('click', exportStatistics);
  elements.resetStats?.addEventListener('click', () => showConfirmDialog(
    'Сброс статистики',
    'Вся статистика будет удалена. Продолжить?',
    resetStatistics
  ));
  
  // Импорт файла
  elements.fileInput?.addEventListener('change', handleFileImport);
  
  // Модальное окно
  elements.confirmCancel?.addEventListener('click', hideConfirmDialog);
  elements.confirmModal?.addEventListener('click', (e) => {
    if (e.target === elements.confirmModal) {
      hideConfirmDialog();
    }
  });
  
  // Предупреждение о несохраненных изменениях
  window.addEventListener('beforeunload', (e) => {
    if (hasUnsavedChanges) {
      e.preventDefault();
      e.returnValue = 'У вас есть несохраненные изменения. Вы уверены, что хотите покинуть страницу?';
    }
  });
}

// Переключение вкладок
function switchTab(tabName) {
  activeTab = tabName;
  
  // Обновляем навигацию
  elements.navTabs.forEach(tab => {
    tab.classList.toggle('active', tab.dataset.tab === tabName);
  });
  
  // Обновляем содержимое
  elements.tabContents.forEach(content => {
    content.classList.toggle('active', content.id === tabName);
  });
  
  // Обновляем статистику при переходе на вкладку статистики
  if (tabName === 'statistics') {
    updateStatistics();
  }
}

// Загрузка данных
async function loadData() {
  try {
    // Загружаем настройки
    const settingsResult = await chrome.storage.sync.get('settings');
    currentSettings = { ...DEFAULT_SETTINGS, ...settingsResult.settings };
    
    // Загружаем статистику
    const statsResult = await chrome.storage.sync.get('statistics');
    currentStatistics = statsResult.statistics || {};
    
    console.log('Settings loaded:', currentSettings);
    console.log('Statistics loaded:', currentStatistics);
    
  } catch (error) {
    console.error('Error loading data:', error);
    showNotification('Ошибка загрузки данных', 'error');
  }
}

// Обновление интерфейса
function updateUI() {
  updateFiltersTab();
  updateNotificationsTab();
  updateAdvancedTab();
  updateStatistics();
}

// Обновление вкладки фильтров
function updateFiltersTab() {
  if (elements.minRatePerMile) elements.minRatePerMile.value = currentSettings.minRatePerMile || 2.5;
  if (elements.maxDeadhead) elements.maxDeadhead.value = currentSettings.maxDeadhead || 50;
  if (elements.minDistance) elements.minDistance.value = currentSettings.minDistance || 200;
  if (elements.maxDistance) elements.maxDistance.value = currentSettings.maxDistance || '';
  
  // Типы оборудования
  elements.equipmentTypes.forEach(checkbox => {
    checkbox.checked = currentSettings.equipmentTypes?.includes(checkbox.value) || false;
  });
  
  // Регионы
  if (elements.regions) {
    elements.regions.value = currentSettings.regions?.join(', ') || '';
  }
}

// Обновление вкладки уведомлений
function updateNotificationsTab() {
  if (elements.notificationFrequency) {
    elements.notificationFrequency.value = currentSettings.notificationFrequency || 'all';
  }
  if (elements.soundAlerts) elements.soundAlerts.checked = currentSettings.soundAlerts !== false;
  if (elements.desktopNotifications) elements.desktopNotifications.checked = currentSettings.desktopNotifications !== false;
  if (elements.persistentNotifications) elements.persistentNotifications.checked = currentSettings.persistentNotifications || false;
  
  if (elements.alertVolume) {
    elements.alertVolume.value = currentSettings.alertVolume || 70;
    document.querySelector('.slider-value').textContent = `${currentSettings.alertVolume || 70}%`;
  }
}

// Обновление расширенных настроек
function updateAdvancedTab() {
  if (elements.scanInterval) elements.scanInterval.value = currentSettings.scanInterval || 3000;
  if (elements.adaptiveScanning) elements.adaptiveScanning.checked = currentSettings.adaptiveScanning !== false;
  if (elements.cacheTimeout) elements.cacheTimeout.value = currentSettings.cacheTimeout || 30;
  if (elements.debugMode) elements.debugMode.checked = currentSettings.debugMode || false;
  if (elements.showIndicator) elements.showIndicator.checked = currentSettings.showIndicator !== false;
}

// Обновление статистики
function updateStatistics() {
  const stats = currentStatistics;
  
  if (elements.totalScansCount) elements.totalScansCount.textContent = formatNumber(stats.totalScans || 0);
  if (elements.totalLoadsCount) elements.totalLoadsCount.textContent = formatNumber(stats.loadsFound || 0);
  if (elements.profitableLoadsCount) elements.profitableLoadsCount.textContent = formatNumber(stats.profitableLoads || 0);
  if (elements.sessionsTotal) elements.sessionsTotal.textContent = formatNumber(stats.sessionsCount || 0);
  
  // Успешность
  if (elements.successRate) {
    const successRate = stats.loadsFound > 0 ? 
      Math.round((stats.profitableLoads / stats.loadsFound) * 100) : 0;
    elements.successRate.textContent = `${successRate}%`;
  }
  
  // Последняя активность
  if (elements.lastActiveTime) {
    if (stats.lastActive) {
      elements.lastActiveTime.textContent = formatDate(stats.lastActive);
    } else {
      elements.lastActiveTime.textContent = 'Никогда';
    }
  }
  
  // Производительность
  if (elements.avgScanInterval) {
    elements.avgScanInterval.textContent = `${currentSettings.scanInterval || 3000}мс`;
  }
  
  if (elements.memoryUsage) {
    // Примерная оценка использования памяти
    const estimatedMemory = Math.round((stats.loadsFound || 0) * 0.5 + (stats.totalScans || 0) * 0.1);
    elements.memoryUsage.textContent = `~${estimatedMemory}KB`;
  }
  
  if (elements.activeCaches) {
    elements.activeCaches.textContent = '1'; // Один основной кеш
  }
}

// Сохранение настроек (улучшенная версия)
async function saveSettings() {
  try {
    updateSaveStatus('Сохранение...', 'info');
    
    const newSettings = collectSettings();
    
    // Валидация собранных настроек перед сохранением
    if (!newSettings || typeof newSettings !== 'object') {
      throw new Error('Неверный формат настроек');
    }
    
    // Проверяем обязательные поля
    const requiredFields = ['minRatePerMile', 'maxDeadhead', 'minDistance', 'equipmentTypes'];
    for (const field of requiredFields) {
      if (newSettings[field] === undefined || newSettings[field] === null) {
        console.warn(`Missing required field: ${field}, using default`);
        newSettings[field] = DEFAULT_SETTINGS[field];
      }
    }
    
    // Сохраняем в storage с retry логикой
    let saveSuccess = false;
    let retryCount = 0;
    const maxRetries = 3;
    
    while (!saveSuccess && retryCount < maxRetries) {
      try {
        await chrome.storage.sync.set({ settings: newSettings });
        saveSuccess = true;
      } catch (storageError) {
        retryCount++;
        console.warn(`Storage save attempt ${retryCount} failed:`, storageError);
        
        if (retryCount < maxRetries) {
          // Ждем немного перед повторной попыткой
          await new Promise(resolve => setTimeout(resolve, 1000 * retryCount));
        } else {
          throw storageError;
        }
      }
    }
    
    currentSettings = newSettings;
    hasUnsavedChanges = false;
    
    // Уведомляем content scripts об изменении настроек
    let scriptsUpdated = 0;
    let scriptsTotal = 0;
    
    try {
      const tabs = await chrome.tabs.query({ 
        url: 'https://freightpower.schneider.com/*' 
      });
      
      scriptsTotal = tabs.length;
      
      if (tabs.length > 0) {
        const updatePromises = tabs.map(async tab => {
          try {
            await chrome.tabs.sendMessage(tab.id, {
              type: 'UPDATE_SETTINGS',
              settings: newSettings
            });
            scriptsUpdated++;
            console.log(`Settings updated for tab ${tab.id}`);
            return true;
          } catch (error) {
            console.warn(`Failed to update settings for tab ${tab.id}:`, error.message);
            return false;
          }
        });
        
        await Promise.allSettled(updatePromises);
      }
      
    } catch (error) {
      console.error('Error updating content scripts:', error);
    }
    
    // Успешное сохранение
    const statusMessage = scriptsTotal > 0 
      ? `Настройки сохранены (обновлено ${scriptsUpdated}/${scriptsTotal} вкладок)`
      : 'Настройки сохранены';
    
    updateSaveStatus(statusMessage, 'success');
    
    console.log('Settings saved successfully:', {
      settings: newSettings,
      tabsUpdated: scriptsUpdated,
      tabsTotal: scriptsTotal
    });
    
  } catch (error) {
    console.error('Error saving settings:', error);
    
    let errorMessage = 'Ошибка сохранения';
    if (error.message.includes('QUOTA_BYTES')) {
      errorMessage = 'Недостаточно места для сохранения';
    } else if (error.message.includes('network')) {
      errorMessage = 'Ошибка сети при сохранении';
    } else if (error.message) {
      errorMessage = `Ошибка: ${error.message}`;
    }
    
    updateSaveStatus(errorMessage, 'error');
    
    // Восстанавливаем предыдущие настройки при ошибке
    try {
      const savedSettings = await chrome.storage.sync.get('settings');
      if (savedSettings.settings) {
        currentSettings = savedSettings.settings;
        updateUI();
      }
    } catch (restoreError) {
      console.error('Failed to restore settings:', restoreError);
    }
  }
}

// Сбор настроек из формы (улучшенная версия)
function collectSettings() {
  const settings = {};
  
  try {
    // Фильтры с валидацией
    const minRate = parseFloat(elements.minRatePerMile?.value);
    settings.minRatePerMile = (!isNaN(minRate) && minRate >= 0) ? minRate : 2.5;
    
    const maxDeadhead = parseInt(elements.maxDeadhead?.value);
    settings.maxDeadhead = (!isNaN(maxDeadhead) && maxDeadhead >= 0) ? maxDeadhead : 50;
    
    const minDistance = parseInt(elements.minDistance?.value);
    settings.minDistance = (!isNaN(minDistance) && minDistance >= 0) ? minDistance : 200;
    
    const maxDistance = elements.maxDistance?.value ? parseInt(elements.maxDistance.value) : null;
    settings.maxDistance = (!isNaN(maxDistance) && maxDistance > 0) ? maxDistance : null;
    
    // Проверяем логику расстояний
    if (settings.maxDistance && settings.maxDistance <= settings.minDistance) {
      console.warn('Max distance should be greater than min distance, setting to null');
      settings.maxDistance = null;
    }
    
    // Типы оборудования
    if (elements.equipmentTypes && elements.equipmentTypes.length > 0) {
      settings.equipmentTypes = Array.from(elements.equipmentTypes)
        .filter(cb => cb && cb.checked)
        .map(cb => cb.value)
        .filter(value => value && value.trim().length > 0);
    } else {
      settings.equipmentTypes = DEFAULT_SETTINGS.equipmentTypes;
    }
    
    // Если ни один тип не выбран, используем все по умолчанию
    if (settings.equipmentTypes.length === 0) {
      settings.equipmentTypes = DEFAULT_SETTINGS.equipmentTypes;
    }
    
    // Регионы с улучшенной обработкой
    try {
      const regionsText = elements.regions?.value || '';
      if (regionsText.trim()) {
        settings.regions = regionsText
          .split(/[,;\n]/) // Поддерживаем разные разделители
          .map(r => r.trim())
          .filter(r => r.length > 0)
          .filter(r => /^[a-zA-Z\s]{1,50}$/.test(r)); // Валидация формата
      } else {
        settings.regions = [];
      }
    } catch (error) {
      console.error('Error parsing regions:', error);
      settings.regions = [];
    }
    
    // Уведомления
    const validFrequencies = ['all', 'high_priority', 'none'];
    const frequency = elements.notificationFrequency?.value || 'all';
    settings.notificationFrequency = validFrequencies.includes(frequency) ? frequency : 'all';
    
    settings.soundAlerts = elements.soundAlerts?.checked !== false;
    settings.desktopNotifications = elements.desktopNotifications?.checked !== false;
    settings.persistentNotifications = elements.persistentNotifications?.checked || false;
    
    const alertVolume = parseInt(elements.alertVolume?.value);
    settings.alertVolume = (!isNaN(alertVolume) && alertVolume >= 0 && alertVolume <= 100) ? alertVolume : 70;
    
    // Расширенные настройки
    const scanInterval = parseInt(elements.scanInterval?.value);
    settings.scanInterval = (!isNaN(scanInterval) && scanInterval >= 1000 && scanInterval <= 60000) ? scanInterval : 3000;
    
    settings.adaptiveScanning = elements.adaptiveScanning?.checked !== false;
    
    const cacheTimeout = parseInt(elements.cacheTimeout?.value);
    settings.cacheTimeout = (!isNaN(cacheTimeout) && cacheTimeout >= 5 && cacheTimeout <= 300) ? cacheTimeout : 30;
    
    settings.debugMode = elements.debugMode?.checked || false;
    settings.showIndicator = elements.showIndicator?.checked !== false;
    
    console.log('Collected settings:', settings);
    
    return settings;
    
  } catch (error) {
    console.error('Error collecting settings:', error);
    updateSaveStatus('Ошибка сбора настроек', 'error');
    return DEFAULT_SETTINGS;
  }
}

// Автосохранение
async function autoSave() {
  if (hasUnsavedChanges && activeTab !== 'statistics') {
    console.log('Auto-saving settings...');
    await saveSettings();
  }
}

// Сброс к настройкам по умолчанию
async function resetToDefaults() {
  currentSettings = { ...DEFAULT_SETTINGS };
  updateUI();
  hasUnsavedChanges = true;
  updateSaveStatus('Настройки сброшены к умолчаниям', 'info');
  hideConfirmDialog();
}

// Сброс настроек
async function resetSettings() {
  try {
    await chrome.storage.sync.remove('settings');
    currentSettings = { ...DEFAULT_SETTINGS };
    updateUI();
    hasUnsavedChanges = false;
    updateSaveStatus('Настройки удалены', 'info');
    hideConfirmDialog();
  } catch (error) {
    console.error('Error resetting settings:', error);
    updateSaveStatus('Ошибка сброса настроек', 'error');
  }
}

// Очистка всех данных
async function clearAllData() {
  try {
    await chrome.storage.sync.clear();
    await chrome.storage.local.clear();
    
    currentSettings = { ...DEFAULT_SETTINGS };
    currentStatistics = {};
    
    updateUI();
    hasUnsavedChanges = false;
    updateSaveStatus('Все данные удалены', 'info');
    hideConfirmDialog();
  } catch (error) {
    console.error('Error clearing data:', error);
    updateSaveStatus('Ошибка очистки данных', 'error');
  }
}

// Сброс статистики
async function resetStatistics() {
  try {
    await chrome.storage.sync.remove('statistics');
    await chrome.storage.local.remove('recentLoads');
    
    currentStatistics = {};
    updateStatistics();
    updateSaveStatus('Статистика сброшена', 'info');
    hideConfirmDialog();
  } catch (error) {
    console.error('Error resetting statistics:', error);
    updateSaveStatus('Ошибка сброса статистики', 'error');
  }
}

// Экспорт настроек
function exportSettings() {
  const data = {
    settings: currentSettings,
    exportDate: new Date().toISOString(),
    version: '1.0.0'
  };
  
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  
  const a = document.createElement('a');
  a.href = url;
  a.download = `freightpower-monitor-settings-${new Date().toISOString().split('T')[0]}.json`;
  a.click();
  
  URL.revokeObjectURL(url);
  updateSaveStatus('Настройки экспортированы', 'success');
}

// Экспорт статистики
function exportStatistics() {
  const data = {
    statistics: currentStatistics,
    settings: currentSettings,
    exportDate: new Date().toISOString(),
    version: '1.0.0'
  };
  
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  
  const a = document.createElement('a');
  a.href = url;
  a.download = `freightpower-monitor-stats-${new Date().toISOString().split('T')[0]}.json`;
  a.click();
  
  URL.revokeObjectURL(url);
  updateSaveStatus('Статистика экспортирована', 'success');
}

// Обработка импорта файла
async function handleFileImport(event) {
  const file = event.target.files[0];
  if (!file) return;
  
  try {
    const text = await file.text();
    const data = JSON.parse(text);
    
    if (data.settings) {
      currentSettings = { ...DEFAULT_SETTINGS, ...data.settings };
      updateUI();
      hasUnsavedChanges = true;
      updateSaveStatus('Настройки импортированы', 'success');
    } else {
      updateSaveStatus('Неверный формат файла', 'error');
    }
  } catch (error) {
    console.error('Error importing settings:', error);
    updateSaveStatus('Ошибка импорта', 'error');
  }
  
  // Сбрасываем input
  event.target.value = '';
}

// Тест звука
function testSound() {
  try {
    const volume = (parseInt(elements.alertVolume?.value) || 70) / 100;
    
    const audioContext = new (window.AudioContext || window.webkitAudioContext)();
    const oscillator = audioContext.createOscillator();
    const gainNode = audioContext.createGain();
    
    oscillator.connect(gainNode);
    gainNode.connect(audioContext.destination);
    
    oscillator.frequency.value = 800;
    oscillator.type = 'sine';
    
    gainNode.gain.setValueAtTime(0, audioContext.currentTime);
    gainNode.gain.linearRampToValueAtTime(volume * 0.3, audioContext.currentTime + 0.01);
    gainNode.gain.linearRampToValueAtTime(0, audioContext.currentTime + 0.5);
    
    oscillator.start(audioContext.currentTime);
    oscillator.stop(audioContext.currentTime + 0.5);
    
    updateSaveStatus('Звук воспроизведен', 'info');
  } catch (error) {
    console.error('Error playing test sound:', error);
    updateSaveStatus('Ошибка воспроизведения', 'error');
  }
}

// Показ диалога подтверждения
function showConfirmDialog(title, message, callback) {
  elements.confirmTitle.textContent = title;
  elements.confirmMessage.textContent = message;
  elements.confirmModal.style.display = 'flex';
  
  // Удаляем старый обработчик
  elements.confirmOk.onclick = null;
  
  // Добавляем новый обработчик
  elements.confirmOk.onclick = callback;
}

// Скрытие диалога подтверждения
function hideConfirmDialog() {
  elements.confirmModal.style.display = 'none';
  elements.confirmOk.onclick = null;
}

// Обновление статуса сохранения
function updateSaveStatus(message, type = 'info') {
  if (!elements.saveStatus) return;
  
  elements.saveStatus.textContent = message;
  elements.saveStatus.className = `save-status ${type}`;
  
  // Скрываем через 3 секунды
  setTimeout(() => {
    if (elements.saveStatus.textContent === message) {
      elements.saveStatus.textContent = '';
      elements.saveStatus.className = 'save-status';
    }
  }, 3000);
}

// Показ уведомления
function showNotification(message, type = 'info') {
  updateSaveStatus(message, type);
}

// Утилиты форматирования
function formatNumber(num) {
  if (num >= 1000000) {
    return (num / 1000000).toFixed(1) + 'M';
  }
  if (num >= 1000) {
    return (num / 1000).toFixed(1) + 'K';
  }
  return num.toString();
}

function formatDate(timestamp) {
  const date = new Date(timestamp);
  const now = new Date();
  const diffMs = now - date;
  const diffDays = Math.floor(diffMs / (24 * 60 * 60 * 1000));
  
  if (diffDays === 0) {
    return 'Сегодня';
  } else if (diffDays === 1) {
    return 'Вчера';
  } else if (diffDays < 7) {
    return `${diffDays} дней назад`;
  } else {
    return date.toLocaleDateString('ru-RU');
  }
}

console.log('Options script initialized');
