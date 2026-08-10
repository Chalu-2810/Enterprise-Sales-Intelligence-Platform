-- The comprehensive analysis view every page in this app queries from.
-- Auto-created on first run by utils/database.py if it doesn't already exist.

CREATE VIEW IF NOT EXISTS vw_app_sales AS
SELECT
    f.Sales_Key, f.Order_ID, f.Order_Line_ID,
    od.Date AS Order_Date, od.Year AS Year, od.Quarter AS Quarter,
    od.Month AS Month, od.Month_Name AS Month_Name,
    r.Region_Name AS Region, r.Country AS Country, r.State AS State, r.City AS City,
    p.Product_Name AS Product, p.Category AS Category, p.Sub_Category AS Sub_Category,
    p.Unit_Cost AS Unit_Cost, p.Unit_Price AS Unit_Price,
    c.Customer_Name AS Customer, c.Segment AS Segment, c.Customer_Rating AS Customer_Rating,
    c.Customer_Key AS Customer_Key,
    sp.Salesperson_Name AS Salesperson, sp.Salesperson_Key AS Salesperson_Key,
    ch.Channel_Name AS Channel,
    f.Quantity AS Quantity, f.Sales_Amount AS Sales_Amount,
    f.Discount_Amount AS Discount_Amount, f.Cost_Amount AS Cost_Amount,
    f.Profit_Amount AS Profit_Amount, f.Shipping_Cost AS Shipping_Cost,
    (f.Sales_Amount - f.Discount_Amount) AS Net_Revenue,
    f.Payment_Mode AS Payment_Mode, f.Is_Returned AS Is_Returned
FROM fact_sales f
JOIN dim_date od ON f.Order_Date_Key = od.Date_Key
JOIN dim_region r ON f.Region_Key = r.Region_Key
JOIN dim_product p ON f.Product_Key = p.Product_Key
JOIN dim_customer c ON f.Customer_Key = c.Customer_Key
JOIN dim_channel ch ON f.Channel_Key = ch.Channel_Key
LEFT JOIN dim_salesperson sp ON f.Salesperson_Key = sp.Salesperson_Key;
