INSERT INTO sales_channels (sales_channel_code, sales_channel_name)
SELECT approved.sales_channel_code, approved.sales_channel_name
FROM (
    VALUES
        ('ECOMMERCE', 'E-Commerce'),
        ('RETAIL', 'Retail')
) AS approved (sales_channel_code, sales_channel_name)
WHERE NOT EXISTS (
    SELECT 1
    FROM sales_channels AS existing
    WHERE existing.sales_channel_code = approved.sales_channel_code
);
