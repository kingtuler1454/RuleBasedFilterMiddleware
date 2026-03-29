import pandas as pd  
import numpy as np  
from sklearn.ensemble import RandomForestClassifier  
from sklearn.model_selection import train_test_split  
from opensearchpy import OpenSearch  
import joblib  
  
def generate_training_data():  
    """Генерация обучающих данных из существующих запросов"""  
    opensearch = OpenSearch(hosts=[{'host': 'localhost', 'port': 9200}])  
      
    # Получаем все запросы  
    search_result = opensearch.search(  
        index="requests",  
        body={"size": 10000, "query": {"match_all": {}}}  
    )  
      
    requests = [req['_source'] for req in search_result['hits']['hits']]  
      
    # Группируем по IP и создаем признаки  
    data = []  
    for ip in set(req['userIp'] for req in requests):  
        ip_requests = [req for req in requests if req['userIp'] == ip]  
          
        # Метки: считаем подозрительными если много запросов за короткое время  
        is_suspicious = len(ip_requests) > 100  # пример критерия  
          
        features = extract_features_from_requests(ip_requests)  
        if features.size > 0:  
            data.append({  
                'features': features.flatten(),  
                'label': 0 if is_suspicious else 1  # 1 = легитимный  
            })  
      
    return data  
  
# Обучение модели  
data = generate_training_data()  
X = np.array([item['features'] for item in data])  
y = np.array([item['label'] for item in data])  
  
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)  
  
model = RandomForestClassifier(n_estimators=100, random_state=42)  
model.fit(X_train, y_train)  
  
print(f"Accuracy: {model.score(X_test, y_test)}")  
  
# Сохраняем модель  
joblib.dump(model, 'intrusion_detection_model.pkl')