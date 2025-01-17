import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Toaster } from "@/components/ui/toaster";
import { useToast } from "@/hooks/use-toast";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

interface Item {
  id: number;
  name: string;
  created_at: string;
}

function App() {
  const [items, setItems] = useState<Item[]>([]);
  const [newItem, setNewItem] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const { toast } = useToast();
  const modalUrl = import.meta.env.VITE_MODAL_URL;
  const fetchItems = async () => {
    try {
      const response = await fetch(`${modalUrl}/items`);
      const data = await response.json();
      setItems(data.items);
    } catch (error) {
      toast({
        variant: "destructive",
        description: "Failed to fetch items",
      });
    }
  };

  useEffect(() => {
    fetchItems();
  }, []);

  const addItem = async () => {
    if (!newItem.trim()) return;

    setIsLoading(true);
    try {
      const response = await fetch(
        `${modalUrl}/items/${encodeURIComponent(newItem)}`,
        {
          method: "POST",
        },
      );

      if (!response.ok) throw new Error("Failed to add item");

      toast({
        description: "Item added successfully",
      });

      setNewItem("");
      fetchItems();
    } catch (error) {
      toast({
        variant: "destructive",
        description: "Failed to add item",
      });
    } finally {
      setIsLoading(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    addItem();
  };

  return (
    <>
      <div className="container mx-auto p-4 space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>Item Manager</CardTitle>
            <CardDescription>
              Add and view items in the database
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="flex gap-4 mb-6">
              <Input
                value={newItem}
                onChange={(e) => setNewItem(e.target.value)}
                placeholder="Enter item name"
                className="flex-1"
              />
              <Button type="submit" disabled={isLoading}>
                {isLoading ? "Adding..." : "Add Item"}
              </Button>
            </form>
            <Table>
              <TableCaption>A list of all items in the database</TableCaption>
              <TableHeader>
                <TableRow>
                  <TableHead>ID</TableHead>
                  <TableHead>Name</TableHead>
                  <TableHead>Created At</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell>{item.id}</TableCell>
                    <TableCell>{item.name}</TableCell>
                    <TableCell>
                      {new Date(item.created_at).toLocaleString()}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>
      <Toaster />
    </>
  );
}

export default App;