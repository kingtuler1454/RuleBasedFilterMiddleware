using RuleBasedFilterLibrary.Core.Services.RequestSequenceAnalysis;
using RuleBasedFilterLibrary.Extensions;
using TestTileApi.CustomSequenceAnalyzers;
using TestTileApi.Utils;

var builder = WebApplication.CreateBuilder(args);

// Add services to the container.

builder.Services.AddControllers();
// Learn more about configuring Swagger/OpenAPI at https://aka.ms/aspnetcore/swashbuckle
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();
builder.Services.AddHttpClient();

var options = new RuleBasedRequestFilterOptions();
builder.Configuration.GetSection("RuleBasedFilter").Bind(options);
options.EnableRequestSequenceValidation = true;
options.OnViolationAction = OnViolationHandler.CreateClearIndexHandler(options);

builder.Services
    .AddRuleBasedRequestFilterServices(options)
    .UseRequestStorage()
    .AddSequenceAnalyzer<MonotonicityAnalyzer>()
    .AddSequenceAnalyzer<NonMonotonicityAnalyzer>()
    .AddSequenceAnalyzer<NonRandomSequenceAnalyzer>();

var app = builder.Build();

// Configure the HTTP request pipeline.
if (app.Environment.IsDevelopment())
{
    app.UseSwagger();
    app.UseSwaggerUI();
}

app.UseRuleBasedFilter();
// иначе Leaflet получает 307 на каждый тайл (mixed / сертификат).
if (!app.Environment.IsDevelopment())
{
    app.UseHttpsRedirection();
}
app.UseAuthorization();
app.MapControllers();

app.Run();
