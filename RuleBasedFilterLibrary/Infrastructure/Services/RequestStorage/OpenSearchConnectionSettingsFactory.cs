using OpenSearch.Client;
using RuleBasedFilterLibrary.Extensions;

namespace RuleBasedFilterLibrary.Infrastructure.Services.RequestStorage;

public static class OpenSearchConnectionSettingsFactory
{
    public static ConnectionSettings Create(RuleBasedRequestFilterOptions options)
    {
        var nodeAddress = new Uri(options.NodeAddress);
        var settings = new ConnectionSettings(nodeAddress)
            .DefaultIndex(options.IndexName);

        if (!string.IsNullOrEmpty(options.OpenSearchUsername))
        {
            settings = settings.BasicAuthentication(
                options.OpenSearchUsername,
                options.OpenSearchPassword ?? string.Empty);
        }

        if (options.OpenSearchSkipServerCertificateValidation)
        {
            settings = settings.ServerCertificateValidationCallback((_, _, _, _) => true);
        }

        return settings;
    }
}
