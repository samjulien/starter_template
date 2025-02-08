import { useState, useEffect } from "react";
import { useToast } from "@/hooks/use-toast";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import TechnicalIssuesChart from "@/components/TechnicalIssuesChart";
import {
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  LineChart,
  Line,
} from "recharts";

interface EvaluationResult {
  prompt: string;
  image_data: string;
  similarity_score: number;
  objective_evaluation: {
    required_elements: Array<{
      element: string;
      present: boolean;
      details: string;
    }>;
    composition_issues: string[];
    technical_issues: string[];
    style_match: boolean;
    overall_score: number;
    evaluation_notes: string;
  };
  feedback: string;
}

interface BatchMetrics {
  avg_similarity_score: number;
  avg_objective_score: number;
  technical_issues_frequency: { [key: string]: number };
}

interface BatchListItem {
  batch_id: string;
  description?: string;
  timestamp: string;
  image_count: number;
}

interface EvaluationResponse {
  batch_id: string;
  description?: string;
  timestamp: string;
  prompts: string[];
  metrics: BatchMetrics;
  results: EvaluationResult[];
}

function EvaluationVisualization() {
  const [batches, setBatches] = useState<BatchListItem[]>([]);
  const [selectedBatch, setSelectedBatch] = useState<EvaluationResponse | null>(
    null,
  );
  const { toast } = useToast();
  const modalUrl = import.meta.env.VITE_MODAL_URL;

  useEffect(() => {
    fetchBatches();
  }, []);

  const fetchBatches = async () => {
    try {
      const response = await fetch(`${modalUrl}/evaluation_batches`);
      if (!response.ok) throw new Error("Failed to fetch batches");
      const data = await response.json();
      setBatches(data);
      if (data.length > 0) {
        await fetchBatchDetails(data[0].batch_id);
      }
    } catch (error) {
      toast({
        variant: "destructive",
        description: "Failed to fetch evaluation batches",
      });
    }
  };
  // Add this inside your EvaluationVisualization component
  const fetchBatchDetails = async (batchId) => {
    try {
      const response = await fetch(`${modalUrl}/evaluation/${batchId}`);
      if (!response.ok) {
        console.error("Batch fetch error:", await response.text());
        throw new Error("Failed to fetch batch details");
      }
      const data = await response.json();

      // Debug logging
      console.log("Full batch data:", data);
      console.log(
        "Technical issues frequency:",
        data.metrics.technical_issues_frequency,
      );
      console.log(
        "Number of issues:",
        Object.keys(data.metrics.technical_issues_frequency).length,
      );

      setSelectedBatch(data);
    } catch (error) {
      console.error("Batch fetch error:", error);
      toast({
        variant: "destructive",
        description: "Failed to fetch batch details",
      });
    }
  };

  const formatSimilarityData = (results: EvaluationResult[]) => {
    return results.map((result, index) => ({
      index: index + 1,
      score: result.similarity_score,
      prompt: result.prompt,
    }));
  };

  return (
    <div className="container mx-auto p-4 space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Evaluation Results Dashboard</CardTitle>
          <CardDescription>
            View and analyze image generation evaluation results
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Select onValueChange={(value) => fetchBatchDetails(value)}>
            <SelectTrigger className="w-full">
              <SelectValue placeholder="Select evaluation batch" />
            </SelectTrigger>
            <SelectContent>
              {batches.map((batch) => (
                <SelectItem key={batch.batch_id} value={batch.batch_id}>
                  Batch ({batch.image_count} images) -{" "}
                  {new Date(batch.timestamp).toLocaleDateString()}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </CardContent>
      </Card>

      {selectedBatch && (
        <Card>
          <CardHeader>
            <CardTitle>
              {selectedBatch.description || "Batch Results"}
            </CardTitle>
            <CardDescription>
              Batch ID: {selectedBatch.batch_id}
              <br />
              Run on: {new Date(selectedBatch.timestamp).toLocaleString()}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Tabs defaultValue="overview">
              <TabsList>
                <TabsTrigger value="overview">Overview</TabsTrigger>
                <TabsTrigger value="prompts">Prompts</TabsTrigger>
                <TabsTrigger value="metrics">Detailed Metrics</TabsTrigger>
                <TabsTrigger value="gallery">Image Gallery</TabsTrigger>
              </TabsList>

              <TabsContent value="prompts">
                <Card>
                  <CardHeader>
                    <CardTitle>Evaluation Prompts</CardTitle>
                    <CardDescription>
                      Prompts used in this evaluation batch
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-2">
                      {selectedBatch.prompts.map((prompt, index) => (
                        <div
                          key={index}
                          className="p-4 rounded-lg bg-secondary"
                        >
                          <p className="font-mono text-sm">{prompt}</p>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              </TabsContent>

              <TabsContent value="overview">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <Card>
                    <CardHeader>
                      <CardTitle>Average Scores</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="space-y-4">
                        <div>
                          <p className="text-sm">Similarity Score</p>
                          <div className="text-3xl font-bold">
                            {selectedBatch.metrics.avg_similarity_score.toFixed(
                              2,
                            )}
                            %
                          </div>
                        </div>
                        <div>
                          <p className="text-sm">Objective Score</p>
                          <div className="text-3xl font-bold">
                            {selectedBatch.metrics.avg_objective_score.toFixed(
                              2,
                            )}
                          </div>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardHeader>
                      <CardTitle>Technical Issues Frequency</CardTitle>
                      <CardDescription>
                        Count of common technical problems across all generated
                        images
                      </CardDescription>
                    </CardHeader>
                    <CardContent>
                      <TechnicalIssuesChart
                        technicalIssuesData={
                          selectedBatch.metrics.technical_issues_frequency
                        }
                      />
                    </CardContent>
                  </Card>
                </div>
              </TabsContent>

              <TabsContent value="metrics">
                <div className="space-y-6">
                  <Card>
                    <CardHeader>
                      <CardTitle>Similarity Scores by Generation</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="h-64">
                        <ResponsiveContainer width="100%" height="100%">
                          <LineChart
                            data={formatSimilarityData(selectedBatch.results)}
                          >
                            <CartesianGrid strokeDasharray="3 3" />
                            <XAxis dataKey="index" />
                            <YAxis domain={[0, 100]} />
                            <Tooltip />
                            <Line
                              type="monotone"
                              dataKey="score"
                              stroke="#8884d8"
                            />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                    </CardContent>
                  </Card>
                </div>
              </TabsContent>

              <TabsContent value="gallery">
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {selectedBatch.results.map((result, index) => (
                    <Card key={index}>
                      <CardContent className="p-4">
                        <img
                          src={`data:image/jpeg;base64,${result.image_data}`}
                          alt={`Generated image ${index + 1}`}
                          className="w-full h-48 object-cover rounded mb-2"
                        />
                        <div className="space-y-2">
                          <p
                            className="font-medium truncate"
                            title={result.prompt}
                          >
                            Prompt: {result.prompt}
                          </p>
                          <div className="flex justify-between text-sm">
                            <span>
                              Similarity: {result.similarity_score.toFixed(2)}%
                            </span>
                            <span>
                              Score:{" "}
                              {result.objective_evaluation.overall_score.toFixed(
                                2,
                              )}
                            </span>
                          </div>
                          <div className="text-sm space-y-1">
                            <p>Required Elements:</p>
                            {result.objective_evaluation.required_elements.map(
                              (elem, i) => (
                                <div
                                  key={i}
                                  className={`flex items-center ${elem.present ? "text-green-600" : "text-red-600"}`}
                                >
                                  <span>
                                    {elem.element}: {elem.present ? "✓" : "✗"}
                                  </span>
                                </div>
                              ),
                            )}
                          </div>
                          {result.objective_evaluation.technical_issues.length >
                            0 && (
                            <div className="text-sm text-red-600">
                              Issues:{" "}
                              {result.objective_evaluation.technical_issues.join(
                                ", ",
                              )}
                            </div>
                          )}
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

export default EvaluationVisualization;
