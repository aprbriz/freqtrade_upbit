const { chromium } = require('playwright');
const path = require('path');

(async () => {
  const browser = await chromium.launch({ headless: true });

  // Window 1: BTC & ETH
  const page1 = await browser.newPage();
  await page1.setViewportSize({ width: 1920, height: 1080 });
  await page1.goto(`file://${path.join(__dirname, 'window1_btc_eth.html')}`);
  await page1.waitForTimeout(1500);
  await page1.screenshot({
    path: path.join(__dirname, 'window1_btc_eth.png'),
    fullPage: false
  });
  console.log('Saved: window1_btc_eth.png');

  // Window 2: XRP + Dashboard
  const page2 = await browser.newPage();
  await page2.setViewportSize({ width: 1920, height: 1080 });
  await page2.goto(`file://${path.join(__dirname, 'window2_xrp_dashboard.html')}`);
  await page2.waitForTimeout(1500);
  await page2.screenshot({
    path: path.join(__dirname, 'window2_xrp_dashboard.png'),
    fullPage: false
  });
  console.log('Saved: window2_xrp_dashboard.png');

  await browser.close();
  console.log('Done!');
})();
