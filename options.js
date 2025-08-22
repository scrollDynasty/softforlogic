// JavaScript для страницы настроек
class OptionsController {
  constructor() {
    this.defaultSettings = {
      minRatePerMile: 2.50,
      maxDeadhead: 50,
      minDistance: 200,
      maxDistance: null,
      equipmentTypes: ['Dry Van', 'Reefer', 'Flatbed'],
      scanInterval: 3000,
      enableNotifications: true,
      enableSound: true
    };
    
    this.init();
  }
  
  async init() {
    await this.loadSettings();
    this.setupEventListeners();
    this.populateForm();
  }
  
  async loadSettings() {
    return new Promise((resolve) => {
      chrome.storage.local.get(['settings'], (result) => {
        this.settings = result.settings || this.defaultSettings;
        resolve();
      });
    });
  }
  
  setupEventListeners() {
    document.getElementById('settingsForm').addEventListener('submit', (e) => {
      e.preventDefault();
      this.saveSettings();
    });
    
    document.getElementById('resetBtn').addEventListener('click', () => {
      this.resetToDefaults();
    });
    
    document.getElementById('clearDataBtn').addEventListener('click', () => {
      this.clearAllData();
    });
  }
  
  populateForm() {
    // Заполняем поля формы реальными данными
    document.getElementById('minRatePerMile').value = this.settings.minRatePerMile;
    document.getElementById('maxDeadhead').value = this.settings.maxDeadhead;
    document.getElementById('minDistance').value = this.settings.minDistance;
    document.getElementById('maxDistance').value = this.settings.maxDistance || '';
    document.getElementById('scanInterval').value = this.settings.scanInterval;
    document.getElementById('enableNotifications').checked = this.settings.enableNotifications;
    document.getElementById('enableSound').checked = this.settings.enableSound;
    
    // Заполняем типы оборудования
    this.settings.equipmentTypes.forEach(type => {
      const checkbox = document.querySelector(`input[value="${type}"]`);
      if (checkbox) {
        checkbox.checked = true;
      }
    });
  }
  
  async saveSettings() {
    try {
      // Собираем данные из формы
      const formData = new FormData(document.getElementById('settingsForm'));
      const newSettings = {
        minRatePerMile: parseFloat(formData.get('minRatePerMile')),
        maxDeadhead: parseInt(formData.get('maxDeadhead')),
        minDistance: parseInt(formData.get('minDistance')),
        maxDistance: formData.get('maxDistance') ? parseInt(formData.get('maxDistance')) : null,
        scanInterval: parseInt(formData.get('scanInterval')),
        enableNotifications: formData.get('enableNotifications') === 'on',
        enableSound: formData.get('enableSound') === 'on',
        equipmentTypes: []
      };
      
      // Собираем выбранные типы оборудования
      const equipmentCheckboxes = document.querySelectorAll('input[name="equipmentTypes"]:checked');
      equipmentCheckboxes.forEach(checkbox => {
        newSettings.equipmentTypes.push(checkbox.value);
      });
      
      // Валидация данных
      if (newSettings.minRatePerMile < 0) {
        throw new Error('Минимальная ставка за милю не может быть отрицательной');
      }
      
      if (newSettings.maxDeadhead < 0) {
        throw new Error('Максимальный deadhead не может быть отрицательным');
      }
      
      if (newSettings.minDistance < 0) {
        throw new Error('Минимальное расстояние не может быть отрицательным');
      }
      
      if (newSettings.maxDistance !== null && newSettings.maxDistance < newSettings.minDistance) {
        throw new Error('Максимальное расстояние не может быть меньше минимального');
      }
      
      if (newSettings.equipmentTypes.length === 0) {
        throw new Error('Выберите хотя бы один тип оборудования');
      }
      
      // Сохраняем настройки
      await new Promise((resolve, reject) => {
        chrome.storage.local.set({ settings: newSettings }, () => {
          if (chrome.runtime.lastError) {
            reject(new Error(chrome.runtime.lastError.message));
          } else {
            resolve();
          }
        });
      });
      
      // Обновляем настройки во всех активных вкладках FreightPower
      await this.updateActiveTabs(newSettings);
      
      this.settings = newSettings;
      this.showMessage('Настройки успешно сохранены!', 'success');
      
    } catch (error) {
      this.showMessage(`Ошибка при сохранении: ${error.message}`, 'error');
    }
  }
  
  async updateActiveTabs(newSettings) {
    try {
      const tabs = await chrome.tabs.query({ url: 'https://freightpower.schneider.com/*' });
      
      for (const tab of tabs) {
        try {
          await chrome.tabs.sendMessage(tab.id, {
            type: 'UPDATE_SETTINGS',
            settings: newSettings
          });
        } catch (error) {
          console.log(`Не удалось обновить настройки в вкладке ${tab.id}:`, error);
        }
      }
    } catch (error) {
      console.log('Ошибка при обновлении вкладок:', error);
    }
  }
  
  async resetToDefaults() {
    if (confirm('Вы уверены, что хотите сбросить все настройки к значениям по умолчанию?')) {
      try {
        await new Promise((resolve, reject) => {
          chrome.storage.local.set({ settings: this.defaultSettings }, () => {
            if (chrome.runtime.lastError) {
              reject(new Error(chrome.runtime.lastError.message));
            } else {
              resolve();
            }
          });
        });
        
        this.settings = this.defaultSettings;
        this.populateForm();
        await this.updateActiveTabs(this.defaultSettings);
        
        this.showMessage('Настройки сброшены к значениям по умолчанию', 'success');
        
      } catch (error) {
        this.showMessage(`Ошибка при сбросе настроек: ${error.message}`, 'error');
      }
    }
  }
  
  async clearAllData() {
    if (confirm('Вы уверены, что хотите очистить все данные мониторинга? Это действие нельзя отменить.')) {
      try {
        await new Promise((resolve, reject) => {
          chrome.storage.local.clear(() => {
            if (chrome.runtime.lastError) {
              reject(new Error(chrome.runtime.lastError.message));
            } else {
              resolve();
            }
          });
        });
        
        // Переустанавливаем настройки по умолчанию
        await new Promise((resolve, reject) => {
          chrome.storage.local.set({
            isMonitoring: false,
            settings: this.defaultSettings,
            statistics: {
              totalLoadsFound: 0,
              profitableLoadsFound: 0,
              lastScanTime: null,
              monitoringStartTime: null
            }
          }, () => {
            if (chrome.runtime.lastError) {
              reject(new Error(chrome.runtime.lastError.message));
            } else {
              resolve();
            }
          });
        });
        
        this.settings = this.defaultSettings;
        this.populateForm();
        
        this.showMessage('Все данные успешно очищены', 'success');
        
      } catch (error) {
        this.showMessage(`Ошибка при очистке данных: ${error.message}`, 'error');
      }
    }
  }
  
  showMessage(message, type = 'success') {
    const statusElement = document.getElementById('statusMessage');
    statusElement.textContent = message;
    statusElement.className = `status-message status-${type}`;
    statusElement.style.display = 'block';
    
    // Скрываем сообщение через 5 секунд
    setTimeout(() => {
      statusElement.style.display = 'none';
    }, 5000);
  }
}

// Инициализация страницы настроек
document.addEventListener('DOMContentLoaded', () => {
  new OptionsController();
});
