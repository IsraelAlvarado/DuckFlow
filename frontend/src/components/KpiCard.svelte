<script>
  export let title = '';
  export let value = '';
  export let description = '';
</script>

<div style="background: #ffffff; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); border: 1px solid #e2e8f0;">
  <h3 style="margin: 0 0 10px 0; font-size: 14px; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em;">{title}</h3>
  <p style="margin: 0 0 5px 0; font-size: 28px; font-weight: bold; color: #0f172a;">{value}</p>
  <small style="color: #94a3b8;">{description}</small>
</div>