import { useQuery } from "@tanstack/react-query";
import { fetchCategories, fetchTickers } from "@/api/tweets";

export function useCategories() {
  return useQuery({
    queryKey: ["categories"],
    queryFn: fetchCategories,
    staleTime: 60_000,
  });
}

export function useTickers() {
  return useQuery({
    queryKey: ["tickers"],
    queryFn: () => fetchTickers(50),
    staleTime: 60_000,
  });
}
