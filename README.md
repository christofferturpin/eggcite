I started this project as part of a series on Reddit’s r/aws called “Doing Stupid Projects Until I Get an AWS Job.” This is the third project in that set. A poster in one of the threads suggested writing a devlog to document my process; that seemed like solid advice, so here we are.

The inspiration for this project came from a user on a previous project’s thread who said, “Make an egg tracker.” Eggs are… interesting; relevant; tasty? So, I went with that. I wanted to incorporate Infrastructure as Code (IaC) and work with live economic datasets in a way that could scale to more complex problems. Originally, I planned to use Amazon QuickSight for visualization, but since that would be too expensive for something I wanted to display publicly and keep running long-term, I pivoted to a more cost-effective solution. Amazon’s helpdesk pay is fine; the idea here is to get AWS to give me money, not the other way around.

Given the focus on cost efficiency, pricing constraints influenced nearly every technical decision. One of the first considerations was data sourcing. While major grocers like Wal-Mart bury their pricing behind multiple layers of blockers, Kroger offers a free, publicly available API; that made it the clear choice. (I even joked with my wife about doing our grocery shopping programmatically this weekend.)

To keep hosting costs low, I went fully serverless. At the core of the setup is an AWS Lambda function that, using an Amazon EventBridge scheduled trigger, fetches the daily price for a dozen Kroger-brand Grade A large white eggs. The data is stored in an S3 bucket as a CSV and used to generate an HTML report; that report is then updated and published to S3 once a day.

The entire deployment is automated using AWS SAM, making it easy to modify or redeploy. One of the key features I added is custom UPC tracking, allowing users to swap out the default egg UPC for any other item Kroger’s API supports; this makes the system more flexible, effectively turning it into a general-purpose price tracker.

Operational Excellence

The project is designed to be fully automated. AWS SAM streamlines deployment, while EventBridge triggers the Lambda function once per day without requiring external cron jobs. Logging is handled via CloudWatch, allowing for easy monitoring and debugging; since EventBridge does not automatically retry failed Lambda invocations, any failure handling would need to be built into the Lambda itself, but for now, a simple error log suffices.

Security

The Lambda function follows the principle of least privilege, having access only to the specific S3 bucket and CloudWatch logs it needs. API keys for Kroger are stored securely in AWS Secrets Manager rather than being hardcoded. The generated HTML report is hosted on S3 with public read-only access restricted to just that file; this prevents unauthorized modifications.

Reliability

This project relies on serverless services that automatically scale and handle failures. S3 ensures high durability for price history data. If Kroger’s API is temporarily unavailable, the system will retain previous price data instead of breaking; since EventBridge does not retry failures, a future enhancement could be adding a retry mechanism within the Lambda function.

Performance Efficiency

The system is built to be as lightweight as possible. Lambda runs only when needed, keeping costs low. S3 serves static HTML, eliminating the need for a backend server; there’s no database, which reduces complexity and further optimizes cost.

Cost Optimization

Every choice in this project prioritizes low cost. AWS Lambda usage remains within free-tier limits for normal use. S3 storage is extremely cheap since it only holds a small CSV file and an HTML page; by skipping QuickSight, I’ve kept monthly costs effectively at zero while still providing useful price tracking.

Thoughts and Musings

One thing I kept thinking about during this project was whether Lambda really is the cheapest option for this kind of workload. Serverless is great because it scales down to zero, but given that this function runs once a day and isn't particularly time-sensitive, I wonder if a spot EC2 instance could be a viable alternative. With the right lifecycle management, I could potentially spin up a cheap spot instance, run the job, and shut it down; maybe even at a lower cost than Lambda over time. It would add complexity, but it’s an interesting trade-off to consider.

Another idea that came up while troubleshooting the data collection was scraping price data using a headless browser and AI-based text recognition. Many retailers, especially large ones like Wal-Mart, block API access or require annoying authentication hurdles to access pricing data; but if a browser can render it, an AI can read it. A simple approach could be taking automated screenshots of price listings, then running them through OCR (Optical Character Recognition) or a vision-based AI model to extract the price. That method would be resilient against changes in site structure and could be generalized for almost any product from any retailer. It feels like the kind of approach that’s both incredibly dumb and oddly effective; which fits the spirit of this whole project.

These are the sorts of ideas that pop up when working through a problem like this. Even if they don’t make it into this version of the project, they’re worth tucking away for future experiments.
