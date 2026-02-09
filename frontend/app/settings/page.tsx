"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Header from "@/components/Header";
import Button from "@/components/Button";
import Input from "@/components/Input";
import Alert from "@/components/Alert";
import { Card, CardBody, CardHeader, CardFooter } from "@/components/Card";
import { api, isAuthenticated, getUser } from "@/lib/api";
import { APIKey, Budget, User, Webhook, Tag } from "@/types";
import { copyToClipboard, formatDate } from "@/lib/utils";

const PROVIDERS = ["openai", "anthropic", "google"] as const;

export default function SettingsPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [apiKeys, setApiKeys] = useState<APIKey[]>([]);
  const [budgets, setBudgets] = useState<Budget[]>([]);
  const [budgetLimit, setBudgetLimit] = useState(100);
  const [alertThreshold, setAlertThreshold] = useState(80);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [successMessage, setSuccessMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");

  // New key form
  const [showNewKeyInput, setShowNewKeyInput] = useState(false);
  const [newKeyProvider, setNewKeyProvider] = useState<string>("openai");
  const [newKeyApiKey, setNewKeyApiKey] = useState("");
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // Webhook state
  const [webhooks, setWebhooks] = useState<Webhook[]>([]);
  const [showNewWebhook, setShowNewWebhook] = useState(false);
  const [newWebhookUrl, setNewWebhookUrl] = useState("");
  const [newWebhookEvent, setNewWebhookEvent] = useState<string>("budget_warning");

  // Tags state
  const [tags, setTags] = useState<Tag[]>([]);
  const [showNewTag, setShowNewTag] = useState(false);
  const [newTagName, setNewTagName] = useState("");
  const [newTagColor, setNewTagColor] = useState("#6366f1");

  useEffect(() => {
    if (!isAuthenticated()) {
      router.push("/");
      return;
    }
    loadSettings();
  }, [router]);

  const loadSettings = async () => {
    try {
      setIsLoading(true);
      setErrorMessage("");

      const storedUser = getUser();
      if (storedUser) {
        setUser(storedUser);
      }

      // Load real data from API
      const [keys, budgetList, webhookList, tagList] = await Promise.all([
        api.getKeys().catch(() => [] as APIKey[]),
        api.getBudgets().catch(() => [] as Budget[]),
        api.getWebhooks().catch(() => [] as Webhook[]),
        api.getTags().catch(() => [] as Tag[]),
      ]);

      setApiKeys(keys);
      setBudgets(budgetList);
      setWebhooks(webhookList);
      setTags(tagList);

      if (budgetList.length > 0) {
        setBudgetLimit(budgetList[0].amount_usd);
        setAlertThreshold(budgetList[0].alert_threshold);
      }
    } catch (error) {
      console.error("Failed to load settings:", error);
      setErrorMessage("Failed to load settings. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

  const showSuccess = (msg: string) => {
    setSuccessMessage(msg);
    setTimeout(() => setSuccessMessage(""), 3000);
  };

  const handleCreateApiKey = async () => {
    if (!newKeyApiKey.trim()) return;

    try {
      setIsSaving(true);
      setErrorMessage("");
      const newKey = await api.createKey(newKeyProvider, newKeyApiKey);
      setApiKeys([...apiKeys, newKey]);
      setNewKeyApiKey("");
      setNewKeyProvider("openai");
      setShowNewKeyInput(false);
      showSuccess(`${newKeyProvider} key created successfully. Use the proxy key in your apps.`);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Failed to create API key");
    } finally {
      setIsSaving(false);
    }
  };

  const handleDeleteApiKey = async (id: string) => {
    if (!confirm("Are you sure you want to delete this API key?")) return;

    try {
      setIsSaving(true);
      setErrorMessage("");
      await api.deleteKey(id);
      setApiKeys(apiKeys.filter((key) => key.id !== id));
      showSuccess("API key deleted");
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Failed to delete API key");
    } finally {
      setIsSaving(false);
    }
  };

  const handleCopyKey = async (key: string, id: string) => {
    const success = await copyToClipboard(key);
    if (success) {
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 2000);
    }
  };

  const handleSaveBudget = async () => {
    try {
      setIsSaving(true);
      setErrorMessage("");
      const budget = await api.createBudget(budgetLimit, alertThreshold);
      setBudgets([budget]);
      showSuccess("Budget updated successfully");
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Failed to update budget");
    } finally {
      setIsSaving(false);
    }
  };

  const handleCreateWebhook = async () => {
    if (!newWebhookUrl.trim()) return;

    try {
      setIsSaving(true);
      setErrorMessage("");
      const webhook = await api.createWebhook(newWebhookUrl, newWebhookEvent);
      setWebhooks([...webhooks, webhook]);
      setNewWebhookUrl("");
      setNewWebhookEvent("budget_warning");
      setShowNewWebhook(false);
      showSuccess("Webhook created successfully");
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Failed to create webhook");
    } finally {
      setIsSaving(false);
    }
  };

  const handleDeleteWebhook = async (id: string) => {
    if (!confirm("Are you sure you want to delete this webhook?")) return;

    try {
      setIsSaving(true);
      setErrorMessage("");
      await api.deleteWebhook(id);
      setWebhooks(webhooks.filter((w) => w.id !== id));
      showSuccess("Webhook deleted");
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Failed to delete webhook");
    } finally {
      setIsSaving(false);
    }
  };

  const handleCreateTag = async () => {
    if (!newTagName.trim()) return;

    try {
      setIsSaving(true);
      setErrorMessage("");
      const tag = await api.createTag(newTagName.trim(), newTagColor);
      setTags([...tags, tag]);
      setNewTagName("");
      setNewTagColor("#6366f1");
      setShowNewTag(false);
      showSuccess("Tag created successfully");
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Failed to create tag");
    } finally {
      setIsSaving(false);
    }
  };

  const handleDeleteTag = async (id: string) => {
    if (!confirm("Are you sure you want to delete this tag?")) return;

    try {
      setIsSaving(true);
      setErrorMessage("");
      await api.deleteTag(id);
      setTags(tags.filter((t) => t.id !== id));
      showSuccess("Tag deleted");
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Failed to delete tag");
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) {
    return (
      <>
        <Header showNav={true} user={user ? { name: user.username || user.email, email: user.email } : undefined} />
        <div className="flex items-center justify-center min-h-screen">
          <div className="text-center">
            <div className="inline-block animate-spin rounded-full h-8 w-8 border-2 border-slate-300 border-t-slate-900 dark:border-slate-600 dark:border-t-white" />
            <p className="mt-4 text-slate-600 dark:text-slate-400">Loading settings...</p>
          </div>
        </div>
      </>
    );
  }

  const headerUser = user ? { name: user.username || user.email, email: user.email } : undefined;

  return (
    <>
      <Header showNav={true} user={headerUser} />

      <main className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-slate-900 dark:text-slate-50 mb-2">
            Settings
          </h1>
          <p className="text-slate-600 dark:text-slate-400">
            Manage your API keys, budget, and alerts
          </p>
        </div>

        {successMessage && (
          <Alert variant="success" title="Success" className="mb-6">
            {successMessage}
          </Alert>
        )}

        {errorMessage && (
          <Alert variant="error" title="Error" className="mb-6">
            {errorMessage}
          </Alert>
        )}

        {/* API Keys Section */}
        <Card variant="elevated" className="mb-8">
          <CardHeader title="Provider API Keys" subtitle="Store your real API keys securely. You'll receive proxy keys to use in your apps." />
          <CardBody className="space-y-4">
            {apiKeys.length > 0 ? (
              <div className="space-y-3">
                {apiKeys.map((apiKey) => (
                  <div
                    key={apiKey.id}
                    className="flex items-center justify-between p-4 bg-slate-50 dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700"
                  >
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="px-2 py-0.5 text-xs font-medium rounded bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300">
                          {apiKey.provider}
                        </span>
                        {apiKey.is_active ? (
                          <span className="px-2 py-0.5 text-xs font-medium rounded bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300">
                            Active
                          </span>
                        ) : (
                          <span className="px-2 py-0.5 text-xs font-medium rounded bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300">
                            Inactive
                          </span>
                        )}
                      </div>
                      <p className="text-sm text-slate-500 dark:text-slate-400 font-mono mt-1">
                        {apiKey.proxy_key}
                      </p>
                      {apiKey.last_used_at && (
                        <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                          Last used: {formatDate(apiKey.last_used_at)}
                        </p>
                      )}
                    </div>
                    <div className="flex gap-2">
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => handleCopyKey(apiKey.proxy_key, apiKey.id)}
                      >
                        {copiedId === apiKey.id ? "Copied!" : "Copy Proxy Key"}
                      </Button>
                      <Button
                        variant="danger"
                        size="sm"
                        onClick={() => handleDeleteApiKey(apiKey.id)}
                      >
                        Delete
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-center py-8 text-slate-500 dark:text-slate-400">
                No API keys yet. Add one to start tracking costs.
              </p>
            )}

            {showNewKeyInput ? (
              <div className="space-y-3 p-4 bg-slate-50 dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700">
                <div>
                  <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                    Provider
                  </label>
                  <select
                    value={newKeyProvider}
                    onChange={(e) => setNewKeyProvider(e.target.value)}
                    className="w-full px-3 py-2 bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-600 rounded-lg text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    {PROVIDERS.map((p) => (
                      <option key={p} value={p}>
                        {p.charAt(0).toUpperCase() + p.slice(1)}
                      </option>
                    ))}
                  </select>
                </div>
                <Input
                  label="API Key"
                  placeholder={`Your ${newKeyProvider} API key (e.g., sk-...)`}
                  value={newKeyApiKey}
                  onChange={(e) => setNewKeyApiKey(e.target.value)}
                  type="password"
                />
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  Your key is encrypted before storage and never exposed again.
                </p>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    isLoading={isSaving}
                    onClick={handleCreateApiKey}
                  >
                    Store Key
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => {
                      setShowNewKeyInput(false);
                      setNewKeyApiKey("");
                    }}
                  >
                    Cancel
                  </Button>
                </div>
              </div>
            ) : (
              <Button
                variant="secondary"
                className="w-full"
                onClick={() => setShowNewKeyInput(true)}
              >
                Add Provider Key
              </Button>
            )}
          </CardBody>
        </Card>

        {/* Budget Settings */}
        <Card variant="elevated" className="mb-8">
          <CardHeader title="Budget" subtitle="Set your monthly spending limit and alert threshold" />
          <CardBody className="space-y-4">
            <Input
              label="Monthly Budget Limit ($)"
              type="number"
              value={budgetLimit}
              onChange={(e) => setBudgetLimit(parseFloat(e.target.value) || 0)}
              helper="Set a monthly limit for your AI API spending"
            />
            <Input
              label="Alert Threshold (%)"
              type="number"
              value={alertThreshold}
              onChange={(e) => setAlertThreshold(parseFloat(e.target.value) || 80)}
              helper="Get warned when spending reaches this percentage of your budget"
            />
            {budgets.length > 0 && (
              <div className="p-3 bg-slate-50 dark:bg-slate-800 rounded-lg">
                <p className="text-sm text-slate-600 dark:text-slate-400">
                  Current spend: <span className="font-semibold text-slate-900 dark:text-white">${budgets[0].current_spend.toFixed(2)}</span>
                  {' / '}
                  <span className="font-semibold text-slate-900 dark:text-white">${budgets[0].amount_usd.toFixed(2)}</span>
                  {' '}
                  <span className={`inline-block px-2 py-0.5 text-xs font-medium rounded ${
                    budgets[0].status === 'exceeded' ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300' :
                    budgets[0].status === 'warning' ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300' :
                    'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300'
                  }`}>
                    {budgets[0].status}
                  </span>
                </p>
              </div>
            )}
          </CardBody>
          <CardFooter>
            <Button
              isLoading={isSaving}
              onClick={handleSaveBudget}
            >
              Save Budget
            </Button>
          </CardFooter>
        </Card>

        {/* Alert Webhooks Section */}
        <Card variant="elevated" className="mb-8">
          <CardHeader title="Alert Webhooks" subtitle="Get notified when spending reaches your budget thresholds" />
          <CardBody className="space-y-4">
            {webhooks.length > 0 ? (
              <div className="space-y-3">
                {webhooks.map((webhook) => (
                  <div
                    key={webhook.id}
                    className="flex items-center justify-between p-4 bg-slate-50 dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700"
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className={`px-2 py-0.5 text-xs font-medium rounded ${
                          webhook.event_type === 'budget_exceeded'
                            ? 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300'
                            : webhook.event_type === 'budget_warning'
                            ? 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300'
                            : 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300'
                        }`}>
                          {webhook.event_type.replace('_', ' ')}
                        </span>
                        {webhook.is_active && (
                          <span className="px-2 py-0.5 text-xs font-medium rounded bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300">
                            Active
                          </span>
                        )}
                      </div>
                      <p className="text-sm text-slate-600 dark:text-slate-400 font-mono truncate">
                        {webhook.url}
                      </p>
                    </div>
                    <Button
                      variant="danger"
                      size="sm"
                      onClick={() => handleDeleteWebhook(webhook.id)}
                      className="ml-2 shrink-0"
                    >
                      Delete
                    </Button>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-center py-6 text-slate-500 dark:text-slate-400">
                No webhooks configured. Add one to receive budget alerts.
              </p>
            )}

            {showNewWebhook ? (
              <div className="space-y-3 p-4 bg-slate-50 dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700">
                <Input
                  label="Webhook URL"
                  placeholder="https://your-server.com/webhooks/llmlab"
                  value={newWebhookUrl}
                  onChange={(e) => setNewWebhookUrl(e.target.value)}
                  type="url"
                />
                <div>
                  <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                    Event Type
                  </label>
                  <select
                    value={newWebhookEvent}
                    onChange={(e) => setNewWebhookEvent(e.target.value)}
                    className="w-full px-3 py-2 bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-600 rounded-lg text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="budget_warning">Budget Warning (threshold reached)</option>
                    <option value="budget_exceeded">Budget Exceeded (limit crossed)</option>
                    <option value="anomaly">Anomaly Detection</option>
                  </select>
                </div>
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  LLMLab will POST a JSON payload to this URL when the event occurs.
                </p>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    isLoading={isSaving}
                    onClick={handleCreateWebhook}
                  >
                    Add Webhook
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => {
                      setShowNewWebhook(false);
                      setNewWebhookUrl("");
                    }}
                  >
                    Cancel
                  </Button>
                </div>
              </div>
            ) : (
              <Button
                variant="secondary"
                className="w-full"
                onClick={() => setShowNewWebhook(true)}
              >
                Add Webhook
              </Button>
            )}
          </CardBody>
        </Card>

        {/* Tags Section */}
        <Card variant="elevated" className="mb-8">
          <CardHeader title="Project Tags" subtitle="Organize costs by project, feature, or environment" />
          <CardBody className="space-y-4">
            {tags.length > 0 ? (
              <div className="space-y-3">
                {tags.map((tag) => (
                  <div
                    key={tag.id}
                    className="flex items-center justify-between p-4 bg-slate-50 dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700"
                  >
                    <div className="flex items-center gap-3">
                      <div
                        className="w-4 h-4 rounded-full"
                        style={{ backgroundColor: tag.color }}
                      />
                      <div>
                        <p className="text-sm font-medium text-slate-900 dark:text-white">
                          {tag.name}
                        </p>
                        <p className="text-xs text-slate-500 dark:text-slate-400">
                          {tag.usage_count} {tag.usage_count === 1 ? 'log' : 'logs'}
                        </p>
                      </div>
                    </div>
                    <Button
                      variant="danger"
                      size="sm"
                      onClick={() => handleDeleteTag(tag.id)}
                    >
                      Delete
                    </Button>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-center py-6 text-slate-500 dark:text-slate-400">
                No tags yet. Create one to start grouping your costs.
              </p>
            )}

            {showNewTag ? (
              <div className="space-y-3 p-4 bg-slate-50 dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700">
                <Input
                  label="Tag Name"
                  placeholder="e.g. backend, production, feature-x"
                  value={newTagName}
                  onChange={(e) => setNewTagName(e.target.value)}
                />
                <div>
                  <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                    Color
                  </label>
                  <div className="flex items-center gap-2">
                    <input
                      type="color"
                      value={newTagColor}
                      onChange={(e) => setNewTagColor(e.target.value)}
                      className="w-10 h-10 rounded border border-slate-300 dark:border-slate-600 cursor-pointer"
                    />
                    <span className="text-sm text-slate-500 dark:text-slate-400 font-mono">{newTagColor}</span>
                  </div>
                </div>
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  Tags can be auto-applied via the X-LLMLab-Tags header in proxy requests.
                </p>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    isLoading={isSaving}
                    onClick={handleCreateTag}
                  >
                    Create Tag
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => {
                      setShowNewTag(false);
                      setNewTagName("");
                    }}
                  >
                    Cancel
                  </Button>
                </div>
              </div>
            ) : (
              <Button
                variant="secondary"
                className="w-full"
                onClick={() => setShowNewTag(true)}
              >
                Add Tag
              </Button>
            )}
          </CardBody>
        </Card>
      </main>
    </>
  );
}
