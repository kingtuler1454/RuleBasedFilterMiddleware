using OpenSearch.Client;
using RuleBasedFilterLibrary.Core.Model.Requests;
using RuleBasedFilterLibrary.Extensions;
using RuleBasedFilterLibrary.Infrastructure.Services.RequestStorage;

namespace TestTileApi.Utils;

public static class OnViolationHandler
{
    public static Func<Request, Task> CreateClearIndexHandler(RuleBasedRequestFilterOptions options) =>
        async _ =>
        {
            var config = OpenSearchConnectionSettingsFactory.Create(options);
            var client = new OpenSearchClient(config);
            var deleteRequest = new DeleteIndexRequest(Indices.Parse(options.IndexName));
            await client.Indices.DeleteAsync(deleteRequest);
        };
}
