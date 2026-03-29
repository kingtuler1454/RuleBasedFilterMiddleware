using RuleBasedFilterLibrary.Core.Model.SequenceAnalyses;
using RuleBasedFilterLibrary.Core.Services.RequestSequenceValidation;
using RuleBasedFilterLibrary.Extensions;

namespace TestTileApi.CustomSequenceAnalyzers;

public class MLSequenceAnalyzer : IRequestSequenceAnalyzer
{
    private readonly HttpClient _httpClient;
    private readonly RuleBasedRequestFilterOptions _options;

    public MLSequenceAnalyzer(HttpClient httpClient, RuleBasedRequestFilterOptions options)
    {
        _httpClient = httpClient;
        _options = options;
    }

    public async Task<bool> DidAnalysisSucceed(string userIp, List<ParameterSequenceAnalysis> parameterRules)
    {
        try
        {
            var response = await _httpClient.PostAsJsonAsync("http://localhost:8000/predict", new
            {
                userIp = userIp,
                parameters = parameterRules.Select(p => new { p.Name, p.Type }).ToList()
            });

            var result = await response.Content.ReadFromJsonAsync<MlPredictionResult>();
            return result?.IsLegitimate ?? true;
        }
        catch
        {
            // Если ML сервис недоступен, разрешаем запрос  
            return true;
        }
    }
}

public record MlPredictionResult(bool IsLegitimate);