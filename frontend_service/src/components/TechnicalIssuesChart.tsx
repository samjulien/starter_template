import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from "recharts";

const TechnicalIssuesChart = ({ technicalIssuesData }) => {
  // Transform the data for the chart
  const chartData = Object.entries(technicalIssuesData)
    .map(([issue, count]) => ({
      issue: issue.length > 20 ? issue.substring(0, 20) + "..." : issue,
      count,
      fullIssue: issue,
    }))
    .sort((a, b) => b.count - a.count);

  if (chartData.length === 0) {
    return (
      <div className="h-48 flex items-center justify-center text-muted-foreground">
        No technical issues reported in this batch
      </div>
    );
  }

  return (
    <div className="h-48">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis
            dataKey="issue"
            angle={-45}
            textAnchor="end"
            height={100}
            interval={0}
          />
          <YAxis
            label={{
              value: "Occurrence Count",
              angle: -90,
              position: "insideLeft",
            }}
          />
          <Tooltip
            content={({ active, payload }) => {
              if (active && payload && payload.length) {
                return (
                  <div className="bg-white p-2 border rounded shadow">
                    <p className="text-sm">{payload[0].payload.fullIssue}</p>
                    <p className="text-sm font-bold">
                      Count: {payload[0].value}
                    </p>
                  </div>
                );
              }
              return null;
            }}
          />
          <Bar dataKey="count" fill="#8884d8" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
};

export default TechnicalIssuesChart;
