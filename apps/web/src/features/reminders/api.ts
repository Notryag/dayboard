import { apiClient, requireApiData } from "@/lib/api/typedClient";
import type { ReminderDelivery, ReminderInboxItem } from "@/lib/api/types";

export async function getReminders(): Promise<ReminderInboxItem[]> {
  const { data } = await apiClient.GET("/api/reminders");
  return requireApiData(data);
}

export async function markReminderRead(reminderId: string): Promise<ReminderDelivery> {
  const { data } = await apiClient.POST("/api/reminders/{delivery_id}/read", {
    params: { path: { delivery_id: reminderId } },
  });
  return requireApiData(data);
}

export async function retryReminder(reminderId: string): Promise<ReminderDelivery> {
  const { data } = await apiClient.POST("/api/reminders/{delivery_id}/retry", {
    params: { path: { delivery_id: reminderId } },
  });
  return requireApiData(data);
}
