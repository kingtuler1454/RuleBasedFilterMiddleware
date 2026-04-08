from fastapi import FastAPI, HTTPException  
from pydantic import BaseModel  
from typing import List, Dict, Any  
import requests  
from opensearchpy import OpenSearch  
import joblib  
import numpy as np  
  
app = FastAPI()  
  
class ParameterRule(BaseModel):  
    name: str  
    type: str  
  
class PredictionRequest(BaseModel):  
    userIp: str  
    parameters: List[ParameterRule]  
  
class PredictionResponse(BaseModel):  
    is_legitimate: bool  
    confidence: float  
  
# Подключение к OpenSearch  
opensearch = OpenSearch(  
    hosts=[{'host': 'localhost', 'port': 9200}],  
    http_auth=('admin', 'admin'),  # если нужна аутентификация  
)  
  
# Загрузка обученной модели  
model = joblib.load('intrusion_detection_model.pkl')  
  
def extract_features_from_requests(requests: List[Dict]) -> np.ndarray:  
    """Извлечение признаков из запросов для ML модели"""  
    if len(requests) < 2:  
        return np.array([])  
      
    features = []  
      
    # Признаки на основе последовательности координат  
    x_coords = [int(req['parameters'].get('x', 0)) for req in requests]  
    y_coords = [int(req['parameters'].get('y', 0)) for req in requests]  
    z_coords = [int(req['parameters'].get('z', 0)) for req in requests]  
      
    # Статистические признаки  
    features.extend([  
        np.std(x_coords),  # разброс по X  
        np.std(y_coords),  # разброс по Y  
        len(set(x_coords)),  # уникальные X  
        len(set(y_coords)),  # уникальные Y  
    ])  
      
    # Признаки скорости запросов  
    if len(requests) > 1:  
        time_diffs = []  
        for i in range(1, len(requests)):  
            prev_time = requests[i-1]['requestTime']  
            curr_time = requests[i]['requestTime']  
            time_diffs.append((curr_time - prev_time).total_seconds())  
          
        features.extend([  
            np.mean(time_diffs),  # средний интервал  
            np.std(time_diffs),   # разброс интервалов  
        ])  
      
    return np.array(features).reshape(1, -1)  
  
@app.post("/predict", response_model=PredictionResponse)  
async def predict(request: PredictionRequest):  
    try:  
        # Получаем последние запросы пользователя из OpenSearch  
        search_result = opensearch.search(  
            index="requests",  
            body={  
                "query": {  
                    "match": {  
                        "userIp": request.userIp  
                    }  
                },  
                "sort": [  
                    {"requestTime": {"order": "desc"}}  
                ],  
                "size": 50  
            }  
        )  
          
        requests = search_result['hits']['hits']  
        if not requests:  
            return PredictionResponse(is_legitimate=True, confidence=0.5)  
          
        # Извлекаем признаки  
        features = extract_features_from_requests([req['_source'] for req in requests])  
          
        if features.size == 0:  
            return PredictionResponse(is_legitimate=True, confidence=0.5)  
          
        # Делаем предсказание  
        prediction = model.predict(features)[0]  
        probability = model.predict_proba(features)[0]  
          
        confidence = max(probability)  
        is_legitimate = prediction == 1  
          
        return PredictionResponse(  
            is_legitimate=is_legitimate,  
            confidence=confidence  
        )  
          
    except Exception as e:  
        raise HTTPException(status_code=500, detail=str(e))  
  
if __name__ == "__main__":  
    import uvicorn  
    uvicorn.run(app, host="0.0.0.0", port=8000)