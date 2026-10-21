package hu.buzsak.monitor;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

public class AlertReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        if (PendingAlerts.ACKNOWLEDGE.equals(intent.getAction())) {
            PendingAlerts.acknowledge(context, intent.getIntExtra("identifier", -1));
        } else if (Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction())) {
            PendingAlerts.restore(context);
        }
    }
}